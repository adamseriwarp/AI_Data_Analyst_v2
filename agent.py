"""AI Data Analyst Agent v2 - Simplified with business_definitions_v2.md."""

import os
import json
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import pandas as pd
from db import execute_query

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load business definitions v2 as context
BUSINESS_DEFINITIONS_PATH = Path(__file__).parent / "business_definitions_v2.md"


def load_business_context() -> str:
    """Load the business definitions document."""
    with open(BUSINESS_DEFINITIONS_PATH, "r") as f:
        return f.read()


SYSTEM_PROMPT = """You are a data analyst assistant for Warp, a logistics/freight company.
Your job is: (1) understand user questions, (2) generate correct SQL, (3) explain results.

═══════════════════════════════════════════════════════════════════════════════
DECISION TREE - Which Table & Logic to Use
═══════════════════════════════════════════════════════════════════════════════

┌─ User asks about REVENUE, COST, or PROFIT?
│  └─ Use `orders` table
│     └─ SUM(revenueAllocation), SUM(costAllocation)
│     └─ Filter: status = 'Complete'
│     └─ ⚠️ DO NOT use profitNumber column - calculate profit as revenue - cost

┌─ User asks about COST BY CARRIER?
│  └─ Use `routes` table
│     └─ SUM(CAST(costAllocation AS DECIMAL(10,2)))
│     └─ Filter: carrierName IS NOT NULL

┌─ User asks about SHIPMENT COUNT for a CUSTOMER?
│  └─ Use `otp_reports` table with mainShipment = 'YES'
│     └─ COUNT(*) WHERE mainShipment = 'YES' AND shipmentStatus = 'Complete'

┌─ User asks about OTP/OTD for a CUSTOMER?
│  └─ Use `otp_reports` table with mainShipment = 'YES'
│     └─ OTP: pickTimeArrived <= pickWindowFrom
│     └─ OTD: dropTimeArrived <= dropWindowFrom

┌─ User asks about OTP/OTD for a CARRIER?
│  └─ Use `otp_reports` table with mainShipment = 'NO'
│     └─ If order has NO rows → use them (carrier-specific performance)
│     └─ If order has only YES row → use that as fallback
│     └─ Same OTP/OTD formulas as above

═══════════════════════════════════════════════════════════════════════════════
DATE HANDLING
═══════════════════════════════════════════════════════════════════════════════

Date columns in otp_reports are stored as strings: 'MM/DD/YYYY HH:MM:SS'
Convert using: STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')

ALWAYS ask user which date they mean:
- pickWindowFrom (scheduled pickup)
- pickTimeArrived (actual pickup arrival)
- dropWindowFrom (scheduled delivery)
- dropTimeArrived (actual delivery arrival)

═══════════════════════════════════════════════════════════════════════════════
CLIENT/CARRIER NAME VALIDATION
═══════════════════════════════════════════════════════════════════════════════

When a user mentions a specific client or carrier name in their question:
1. FIRST call search_clients or search_carriers to validate the name exists
2. If NO matches found: Ask the user to clarify and suggest they check spelling
3. If EXACTLY ONE match: Use that exact name in your query
4. If MULTIPLE matches: List all matches and ask the user which one(s) they want

Example responses:
- No match: "I couldn't find a client matching 'Parcel'. Did you mean 'Parsel Inc'?"
- Multiple matches: "I found multiple clients matching 'Door': DoorDash, Doordash Logistics. Which one(s) would you like to include?"
- Single match: "I found 'DoorDash' in the database. Proceeding with your query..."

⚠️ NEVER assume a client/carrier name is spelled correctly - ALWAYS verify first!

═══════════════════════════════════════════════════════════════════════════════
SQL OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Wrap SQL in ```sql ... ``` code blocks
Limit to 100 rows unless user specifies otherwise
Always filter completed work: status = 'Complete' (orders) or shipmentStatus = 'Complete' (otp_reports)

═══════════════════════════════════════════════════════════════════════════════
VISUALIZATION
═══════════════════════════════════════════════════════════════════════════════

If user wants a chart, add a ```chart``` block with JSON:
```chart
{
    "type": "bar",  // bar, line, pie, scatter
    "x": "column_name",
    "y": "column_name",
    "title": "Chart Title"
}
```

═══════════════════════════════════════════════════════════════════════════════
EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

Q: "What's DoorDash's total revenue?"
A: Use orders table:
```sql
SELECT SUM(revenueAllocation) as total_revenue
FROM orders
WHERE customerName = 'DoorDash' AND status = 'Complete';
```

Q: "How many shipments did CookUnity have in January?"
A: Use otp_reports with mainShipment = 'YES':
```sql
SELECT COUNT(*) as shipments
FROM otp_reports
WHERE clientName = 'CookUnity Inc'
  AND mainShipment = 'YES'
  AND shipmentStatus = 'Complete'
  AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2026-01-01'
  AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') < '2026-02-01';
```

Q: "What's the OTP rate for DoorDash?"
A: Use otp_reports mainShipment = 'YES', count on-time vs total:
```sql
SELECT
    COUNT(*) as total_pickups,
    SUM(CASE WHEN STR_TO_DATE(pickTimeArrived, '%m/%d/%Y %H:%i:%s') 
                  <= STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') 
             THEN 1 ELSE 0 END) as on_time,
    ROUND(100.0 * SUM(CASE WHEN STR_TO_DATE(pickTimeArrived, '%m/%d/%Y %H:%i:%s') 
                               <= STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') 
                          THEN 1 ELSE 0 END) / COUNT(*), 2) as otp_pct
FROM otp_reports
WHERE clientName = 'DoorDash'
  AND mainShipment = 'YES'
  AND shipmentStatus = 'Complete'
  AND pickTimeArrived IS NOT NULL
  AND pickWindowFrom IS NOT NULL;
```

Refer to the BUSINESS DEFINITIONS document for complete details on table structure and join relationships.
"""


def search_clients(search_term: str, limit: int = 10):
    """Search for clients matching a search term."""
    sql = f"""
    SELECT DISTINCT clientName, COUNT(*) as shipment_count
    FROM otp_reports
    WHERE clientName LIKE '%{search_term}%'
    GROUP BY clientName ORDER BY shipment_count DESC LIMIT {limit}
    """
    try:
        df = execute_query(sql)
        return df['clientName'].tolist() if not df.empty else []
    except Exception:
        return []


def search_carriers(search_term: str, limit: int = 10):
    """Search for carriers matching a search term."""
    sql = f"""
    SELECT DISTINCT carrierName, COUNT(*) as shipment_count
    FROM otp_reports
    WHERE carrierName LIKE '%{search_term}%'
    GROUP BY carrierName ORDER BY shipment_count DESC LIMIT {limit}
    """
    try:
        df = execute_query(sql)
        return df['carrierName'].tolist() if not df.empty else []
    except Exception:
        return []


def get_all_clients(limit: int = 50):
    """Get list of all clients ordered by shipment count."""
    sql = f"""
    SELECT DISTINCT clientName, COUNT(*) as shipment_count
    FROM otp_reports
    WHERE clientName IS NOT NULL AND clientName != ''
    GROUP BY clientName ORDER BY shipment_count DESC LIMIT {limit}
    """
    try:
        df = execute_query(sql)
        return df['clientName'].tolist() if not df.empty else []
    except Exception:
        return []


def get_all_carriers(limit: int = 50):
    """Get list of all carriers ordered by shipment count."""
    sql = f"""
    SELECT DISTINCT carrierName, COUNT(*) as shipment_count
    FROM otp_reports
    WHERE carrierName IS NOT NULL AND carrierName != ''
    GROUP BY carrierName ORDER BY shipment_count DESC LIMIT {limit}
    """
    try:
        df = execute_query(sql)
        return df['carrierName'].tolist() if not df.empty else []
    except Exception:
        return []


# Define tools for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_clients",
            "description": "Search for clients matching a search term. Use this to validate client names before generating SQL queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "The client name or partial name to search for"
                    }
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_carriers",
            "description": "Search for carriers matching a search term. Use this to validate carrier names before generating SQL queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "The carrier name or partial name to search for"
                    }
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_clients",
            "description": "Get a list of all clients ordered by shipment count.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_carriers",
            "description": "Get a list of all carriers ordered by shipment count.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]


def handle_tool_call(tool_call):
    """Execute a tool call and return the result."""
    func_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    if func_name == "search_clients":
        result = search_clients(args.get("search_term", ""))
    elif func_name == "search_carriers":
        result = search_carriers(args.get("search_term", ""))
    elif func_name == "get_all_clients":
        result = get_all_clients()
    elif func_name == "get_all_carriers":
        result = get_all_carriers()
    else:
        result = {"error": f"Unknown function: {func_name}"}

    return json.dumps(result) if not isinstance(result, str) else result


def get_agent_response(user_question: str, conversation_history: list = None) -> dict:
    """
    Process a user question and return the agent's response.

    Returns:
        dict with keys: 'response', 'sql', 'data', 'error', 'charts'
    """
    if conversation_history is None:
        conversation_history = []

    # Build messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"BUSINESS DEFINITIONS:\n\n{load_business_context()}"},
    ]

    # Add conversation history
    messages.extend(conversation_history)

    # Add current question
    messages.append({"role": "user", "content": user_question})

    # Get response from OpenAI with tools
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=4000
    )

    # Handle tool calls in a loop
    while response.choices[0].message.tool_calls:
        assistant_message = response.choices[0].message
        messages.append(assistant_message)

        # Process each tool call
        for tool_call in assistant_message.tool_calls:
            tool_result = handle_tool_call(tool_call)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

        # Get next response
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=4000
        )

    assistant_message = response.choices[0].message.content

    # Extract SQL if present
    sql = extract_sql(assistant_message)

    # Extract chart configurations if present
    charts = extract_chart_config(assistant_message)

    result = {
        "response": assistant_message,
        "sql": sql,
        "data": None,
        "error": None,
        "charts": charts
    }

    # If SQL was generated, try to execute it
    if sql:
        try:
            df = execute_query(sql)
            result["data"] = df
        except Exception as e:
            result["error"] = str(e)

    return result


def extract_sql(text: str):
    """Extract SQL from markdown code blocks."""
    pattern = r"```sql\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[0].strip()
    return None


def extract_chart_config(text: str):
    """Extract chart configuration from markdown code blocks."""
    pattern = r"```chart\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    charts = []
    for match in matches:
        try:
            config = json.loads(match.strip())
            charts.append(config)
        except json.JSONDecodeError:
            continue

    return charts if charts else None


if __name__ == "__main__":
    # Quick test
    print("Testing agent v2...")
    result = get_agent_response("What's the total revenue for all customers?")
    print(f"Response: {result['response'][:500]}...")
    if result['sql']:
        print(f"\nSQL: {result['sql']}")
    if result['data'] is not None:
        print(f"\nData shape: {result['data'].shape}")
    if result['error']:
        print(f"\nError: {result['error']}")
