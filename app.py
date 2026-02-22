"""Streamlit Chat Interface for the Warp Data Analyst v2."""

import streamlit as st
import pandas as pd
import altair as alt
from agent import get_agent_response, extract_sql
from db import test_connection
import os


def get_app_password():
    """Get app password from env or secrets."""
    password = os.getenv("APP_PASSWORD", "")
    if not password:
        try:
            password = st.secrets.get("APP_PASSWORD", "")
        except Exception:
            password = ""
    return password


def check_password():
    """Returns True if the user has entered the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == get_app_password():
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.markdown("*Please enter the password to access the app.*")
        return False

    if st.session_state["password_correct"]:
        return True

    st.text_input(
        "Password", type="password", on_change=password_entered, key="password"
    )
    st.error("😕 Password incorrect")
    return False


def create_chart(chart_config: dict, data: pd.DataFrame):
    """Create a chart based on the configuration."""
    chart_type = chart_config.get("type", "bar")
    x_col = chart_config.get("x")
    y_col = chart_config.get("y")
    title = chart_config.get("title", "Chart")

    if not x_col or not y_col:
        st.warning("Chart configuration missing x or y columns")
        return None

    if x_col not in data.columns or y_col not in data.columns:
        st.warning(f"Columns {x_col} or {y_col} not found in data")
        return None

    if chart_type == "bar":
        chart = alt.Chart(data).mark_bar().encode(
            x=alt.X(x_col, sort="-y"),
            y=y_col,
            tooltip=[x_col, y_col]
        ).properties(title=title)
    elif chart_type == "line":
        chart = alt.Chart(data).mark_line().encode(
            x=x_col,
            y=y_col,
            tooltip=[x_col, y_col]
        ).properties(title=title)
    elif chart_type == "pie":
        chart = alt.Chart(data).mark_arc().encode(
            theta=y_col,
            color=x_col,
            tooltip=[x_col, y_col]
        ).properties(title=title)
    elif chart_type == "scatter":
        chart = alt.Chart(data).mark_circle().encode(
            x=x_col,
            y=y_col,
            tooltip=[x_col, y_col]
        ).properties(title=title)
    else:
        chart = alt.Chart(data).mark_bar().encode(
            x=x_col,
            y=y_col,
            tooltip=[x_col, y_col]
        ).properties(title=title)

    return chart


def display_message(message: dict, msg_index: int = 0):
    """Display a chat message with optional data and charts."""
    role = message["role"]
    content = message["content"]

    with st.chat_message(role):
        st.markdown(content)

        if message.get("sql"):
            with st.expander("📝 SQL Query", expanded=False):
                st.code(message["sql"], language="sql")

        if message.get("data") is not None and not message["data"].empty:
            with st.expander("📊 Query Results", expanded=True):
                st.dataframe(message["data"], use_container_width=True)
                csv = message["data"].to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="query_results.csv",
                    mime="text/csv",
                    key=f"download_csv_{msg_index}"
                )

        if message.get("charts"):
            for chart_config in message["charts"]:
                if message.get("data") is not None:
                    chart = create_chart(chart_config, message["data"])
                    if chart:
                        st.altair_chart(chart, use_container_width=True)

        if message.get("error"):
            st.error(f"Query Error: {message['error']}")


def get_feedback_url():
    """Get feedback URL from env or secrets."""
    url = os.getenv("FEEDBACK_FORM_URL", "")
    if not url:
        try:
            url = st.secrets.get("FEEDBACK_FORM_URL", "")
        except Exception:
            url = ""
    return url


def main():
    st.set_page_config(
        page_title="Warp Data Analyst v2",
        page_icon="📊",
        layout="wide"
    )

    if not check_password():
        return

    st.title("📊 Warp Data Analyst v2")
    st.caption("Ask questions about Warp's logistics data in natural language")

    with st.sidebar:
        st.header("Status")
        if test_connection():
            st.success("✅ Database connected")
        else:
            st.error("❌ Database connection failed")
            st.stop()

        st.markdown("---")
        st.markdown("### Example Questions")
        st.markdown("""
        - What's DoorDash's total revenue?
        - How many shipments did CookUnity have?
        - What's the OTP rate for Hello Fresh?
        - Show me top 10 customers by revenue
        - What's the profit margin by customer?
        """)

        feedback_url = get_feedback_url()
        if feedback_url:
            st.markdown("---")
            st.markdown(f"[📝 Submit Feedback]({feedback_url})")

        st.markdown("---")
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for idx, message in enumerate(st.session_state.messages):
        display_message(message, idx)

    if prompt := st.chat_input("Ask a question about Warp's data..."):
        user_message = {"role": "user", "content": prompt}
        st.session_state.messages.append(user_message)
        display_message(user_message, len(st.session_state.messages) - 1)

        conversation_history = []
        for msg in st.session_state.messages[:-1]:
            conversation_history.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        with st.spinner("Thinking..."):
            result = get_agent_response(prompt, conversation_history)

        assistant_message = {
            "role": "assistant",
            "content": result["response"],
            "sql": result.get("sql"),
            "data": result.get("data"),
            "error": result.get("error"),
            "charts": result.get("charts")
        }
        st.session_state.messages.append(assistant_message)
        display_message(assistant_message, len(st.session_state.messages) - 1)


if __name__ == "__main__":
    main()
