# Warp Data Analyst - Business Definitions v2

This document provides the AI Data Analyst with verified business logic for answering data questions.

---

## 0. Quick Reference (USE THIS FIRST)

### Schema - ONLY use columns listed here

**`orders` table:**
- `code`, `customerName`, `status` (values: 'completed', 'canceled', 'created', 'inProgress')
- `revenueAllocation`, `costAllocation` (for revenue/cost - DECIMAL)
- `accessorialRevenue` (for TONU identification - DECIMAL)
- `isCrossDock` (1 = cross-dock, 0 = not cross-dock, NULL = unknown)
- `scheduledPickupTime`, `actualPickupTime` (pickup dates)
- `scheduledDropoffTime`, `actualDropoffTime` (delivery dates)
- ⚠️ status = 'completed' (lowercase, not 'Complete')
- ⚠️ Dates are ISO 8601 format: '2024-11-14T15:15-06:00' → use SUBSTRING(field, 1, 10) for date comparisons

**`otp_reports` table:**
- `orderCode`, `warpId`, `clientName`, `carrierName`
- `mainShipment` ('YES' or 'NO'), `shipmentStatus`
- `pickWindowFrom`, `pickTimeArrived` (pickup dates)
- `dropWindowFrom`, `dropTimeArrived` (delivery dates)
- `revenueAllocationNumber`, `costAllocationNumber` (⚠️ unreliable - use orders table)

**`routes` table:**
- `routeId`, `carrierName`, `costAllocation`
- ⚠️ costAllocation is VARCHAR - use CAST(costAllocation AS DECIMAL(10,2))

### Decision Tree - Which Table & Logic to Use

**REVENUE, COST, or PROFIT?**
→ Use `orders` table
→ SUM(revenueAllocation), SUM(costAllocation)
→ Filter: `status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0)`
→ ⚠️ The second condition captures TONU (Truck Ordered Not Used) charges
→ ⚠️ DO NOT use profitNumber column - calculate profit as revenue - cost
→ ⚠️ For date filtering, use delivery date CASE logic (see Date Handling below)

**COST BY CARRIER?**
→ Use `routes` table
→ SUM(CAST(costAllocation AS DECIMAL(10,2)))
→ Filter: carrierName IS NOT NULL

**PALLET COUNT?** (LTL only - FTL is full truck, pallet count not relevant)
→ Filter: `orders.shipmentType = 'LTL'`
→ Filter: `otp_reports.mainShipment = 'YES'`
→ Use `SUM(otp_reports.pieces)`

**PARCEL COUNT?** (parcels only)
→ Filter: `orders.shipmentType = 'PARCEL'`
→ Filter: `otp_reports.mainShipment = 'YES'`
→ Use `SUM(otp_reports.pieces)`

**TOTAL QUANTITY?** (pallets + parcels)
→ Filter: `otp_reports.mainShipment = 'YES'`
→ Use `SUM(otp_reports.pieces)`

**SHIPMENT COUNT for a CUSTOMER?**
→ Use `otp_reports` table with mainShipment = 'YES'
→ COUNT(*) WHERE mainShipment = 'YES' AND shipmentStatus = 'Complete'

**OTP/OTD for a CUSTOMER?**
→ Use `otp_reports` table with mainShipment = 'YES'
→ OTP: pickTimeArrived <= pickWindowFrom
→ OTD: dropTimeArrived <= dropWindowFrom

**OTP/OTD for a CARRIER?**
→ Use `otp_reports` table with mainShipment = 'NO'
→ If order has NO rows → use them (carrier-specific performance)
→ If order has only YES row → use that as fallback
→ Same OTP/OTD formulas as above

### Date Handling

**For `orders` table (revenue/profit queries):**
- Format: ISO 8601 (e.g., '2024-11-14T15:15-06:00') → use SUBSTRING(field, 1, 10)
- ⚠️ DO NOT use DATE() - it converts to UTC and shifts dates incorrectly!
- ⚠️ For revenue/profit queries, DO NOT ask user - use this CASE logic:
  - If isCrossDock = 0 AND actualDropoffTime exists → use actualDropoffTime
  - Otherwise → use scheduledDropoffTime

```sql
CASE
  WHEN isCrossDock = 0 AND actualDropoffTime IS NOT NULL AND actualDropoffTime != ''
    THEN SUBSTRING(actualDropoffTime, 1, 10)
  ELSE SUBSTRING(scheduledDropoffTime, 1, 10)
END
```

**For `otp_reports` table (shipment count, OTP/OTD queries):**
- Format: 'MM/DD/YYYY HH:MM:SS' → use STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')
- ⚠️ ASK user which date field to use:
  1. Scheduled pickup date (pickWindowFrom)
  2. Actual pickup date (pickTimeArrived)
  3. Scheduled delivery date (dropWindowFrom)
  4. Actual delivery date (dropTimeArrived)

---

## 1. Overview

**Database**: `datahub` (MySQL)

### 1.1 Key Tables

| Table | ~Rows | Primary Use |
|-------|-------|-------------|
| `orders` | 304k | Revenue, cost, profit (source of truth) |
| `otp_reports` | 675k | OTP/OTD performance, shipment details, carrier/customer info |
| `routes` | 262k | Route/load assignments to carriers |

### 1.2 Key Identifier Patterns

| ID Type | Format | Example | Description |
|---------|--------|---------|-------------|
| **orderCode** | `P-XXXXX-YYYY` or `O-XXXX-YYYY` | `P-02078-2452` | Parent order ID |
| **warpId** | `S-XXXXXX` | `S-385753` | Individual shipment ID |
| **loadId/routeId** | `XXXX-YYYY` | `1513-2445` | Route/load identifier |

### 1.3 Join Relationships

```
otp_reports (PRIMARY - use for most queries)
    ├── orderCode → orders.code ✓ (1:1 per order)
    ├── loadId → routes.routeId ✓ (1:1 per route)
    ├── carrierName → text match (no FK)
    └── clientName → text match (no FK)

orders (order-level data)
    ├── code = orderCode
    └── customerName, revenueAllocation, costAllocation

routes (route/load data)
    ├── routeId = loadId
    └── carrierName, costAllocation
```

### 1.4 otp_reports Column Categories

**Identifiers:**
- `id`, `warpId`, `orderCode`, `orderId`, `code`, `loadId`, `clientId`

**Customer/Carrier Info:**
- `clientName`, `carrierName`, `driverName`
- `accountOwner`, `salesRep`, `clientSuccessRep`, `carrierSaleRep`

**Pickup Data:**
- `pickAddress`, `pickCity`, `pickState`, `pickZipcode`, `pickLocationName`
- `pickWindowFrom`, `pickWindowTo` (scheduled window)
- `pickTimeArrived`, `pickTimeDeparted` (actual times)
- `pickStatus`, `pickupDelayCode`

**Dropoff Data:**
- `dropAddress`, `dropCity`, `dropState`, `dropZipcode`, `dropLocationName`
- `dropWindowFrom`, `dropWindowTo` (scheduled window)
- `dropTimeArrived`, `dropTimeDeparted` (actual times)
- `dropStatus`, `deliveryDelayCode`

**Financial:**
- `revenueAllocationNumber`, `costAllocationNumber`
- ⚠️ `profitNumber` - DO NOT USE (data quality issues)

**Shipment Classification:**
- `mainShipment` (YES/NO), `shipmentType`, `shipmentStatus`, `loadStatus`
- `equipment`, `startMarket`, `endMarket`

**Time/Date:**
- `createdAt`, `revenueDate`, `revenueMonth`
- `loadBookedTime`

---

## 2. Calculation Rules

### 2.1 Revenue / Cost / Profit

**Rule: ALWAYS use the `orders` table.**

```sql
SELECT
    code as orderCode,
    revenueAllocation as revenue,
    costAllocation as cost,
    revenueAllocation - costAllocation as profit
FROM orders
WHERE status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0)
```

**Status Filter (TONU):**
- Use `status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0)`
- The second condition captures **TONU (Truck Ordered Not Used)** charges - canceled orders that still incur charges
- ⚠️ Note: status values are **lowercase** ('completed', not 'Complete')

**Why not use `otp_reports` for revenue/cost?**

Revenue and cost in `otp_reports` may be recorded on multiple rows per order, and the recording pattern varies by client. Some clients record revenue only on `mainShipment = 'NO'` rows, others duplicate it on both YES and NO rows. Summing `otp_reports` rows can result in over-counting or under-counting.

The `orders` table has **one authoritative value per order**, regardless of:
- LTL vs FTL
- Single-leg vs multi-leg shipments
- Which client
- `mainShipment` value

**Example - Revenue by Customer:**
```sql
SELECT
    customerName,
    SUM(revenueAllocation) as total_revenue,
    SUM(costAllocation) as total_cost,
    SUM(revenueAllocation - costAllocation) as total_profit
FROM orders
WHERE status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0)
GROUP BY customerName
ORDER BY total_revenue DESC;
```

**⚠️ Warning**: Do NOT use the `profitNumber` column - it has data quality issues. Always calculate profit as `revenueAllocation - costAllocation`.

---

### 2.2 Cost from a Carrier

**Rule: Use the `routes` table.**

```sql
SELECT
    carrierName,
    SUM(CAST(costAllocation AS DECIMAL(10,2))) as total_cost
FROM routes
WHERE carrierName IS NOT NULL
  AND carrierName != ''
GROUP BY carrierName
ORDER BY total_cost DESC;
```

**Why `routes` and not `orders` or `otp_reports`?**

- The `orders` table has no carrier information
- The `routes` table has one row per route, with one carrier and one cost value
- No deduplication needed - each route is a single record
- Verified: `routes.costAllocation` matches `SUM(otp_reports.costAllocationNumber)` for the same route

**Note**: ~10% of routes have missing carrier names. Filter these out with `WHERE carrierName IS NOT NULL AND carrierName != ''`.

---

### 2.3 Date Filtering

#### For `orders` table (Revenue/Profit queries):

**Rule:** Use the **delivery date** determined by cross-dock logic (DO NOT ask the user):

| isCrossDock | actualDropoffTime | Date Field to Use |
|-------------|-------------------|-------------------|
| 1 or NULL | Any | `scheduledDropoffTime` |
| 0 | Has value | `actualDropoffTime` |
| 0 | Empty/NULL | `scheduledDropoffTime` |

**CASE expression for date filtering:**
```sql
CASE
  WHEN isCrossDock = 0 AND actualDropoffTime IS NOT NULL AND actualDropoffTime != ''
    THEN SUBSTRING(actualDropoffTime, 1, 10)
  ELSE SUBSTRING(scheduledDropoffTime, 1, 10)
END
```

**⚠️ Important:**
- Dates in `orders` table are ISO 8601 format (e.g., `2024-11-14T15:15-06:00`)
- Use `SUBSTRING(field, 1, 10)` to extract the date portion
- **DO NOT use `DATE()`** - it converts to UTC first, causing late-evening orders to shift to the next day

**Example - Profit with date range:**
```sql
SELECT
    customerName,
    SUM(revenueAllocation) as total_revenue,
    SUM(costAllocation) as total_cost,
    SUM(revenueAllocation - costAllocation) as total_profit
FROM orders
WHERE customerName = 'DoorDash'
  AND (status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0))
  AND (
    CASE
      WHEN isCrossDock = 0 AND actualDropoffTime IS NOT NULL AND actualDropoffTime != ''
        THEN SUBSTRING(actualDropoffTime, 1, 10)
      ELSE SUBSTRING(scheduledDropoffTime, 1, 10)
    END
  ) BETWEEN '2026-01-01' AND '2026-01-04';
```

#### For `otp_reports` table (Shipment Count, OTP/OTD queries):

**Rule:** Ask the user which date field to filter on.

| Field | Meaning | Use When |
|-------|---------|----------|
| `pickWindowFrom` | When pickup was **scheduled** | Analyzing planned/booked shipments |
| `pickTimeArrived` | When driver **arrived** at pickup | Analyzing actual pickup timing |
| `dropWindowFrom` | When delivery was **scheduled** | Analyzing planned delivery dates |
| `dropTimeArrived` | When driver **arrived** at delivery | Analyzing actual delivery timing |

**Example prompt to user:**
> "Which date field should I use?
> 1. Scheduled pickup date
> 2. Actual pickup date
> 3. Scheduled delivery date
> 4. Actual delivery date"

**Note:** Use `STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')` for date parsing in `otp_reports`.

---

## 3. Questions to Investigate

The following sections will be filled in as we verify the correct approach for each:

### 3.3 Revenue/Cost for a Lane
*TODO: Investigate*

### 3.4 Shipment Count per Customer

**Rule:** Use `otp_reports` table, count `mainShipment = 'YES'` rows.

```sql
SELECT
    clientName,
    COUNT(*) as shipment_count
FROM otp_reports
WHERE mainShipment = 'YES'
  AND clientName IS NOT NULL
  AND clientName != ''
GROUP BY clientName
ORDER BY shipment_count DESC;
```

**Why not use `orders` table?**

One order can contain multiple shipments (especially for LTL consolidation customers). Examples:
- DoorDash: 17K orders → 32K shipments (1.8x)
- Sharing Excess: 3K orders → 15K shipments (4.7x)

The `orders` table has one row per order, but `otp_reports` captures each individual shipment as a `mainShipment = 'YES'` row.

**Note:** `otp_reports.clientName` ≈ `orders.customerName` (99.97% match rate)

### 3.5 Routes Completed by Carrier
*TODO: Investigate*

### 3.5.1 Shipments Completed by Carrier
*TODO: Investigate*

### 3.6 OTP/OTD for Customers

**Rule:** Use `otp_reports` table with `mainShipment = 'YES'` rows.

**Definitions:**
- **OTP (On Time Pickup):** `pickTimeArrived <= pickWindowFrom`
- **OTD (On Time Delivery):** `dropTimeArrived <= dropWindowFrom`

```sql
SELECT
    clientName,
    COUNT(*) as total_shipments,
    SUM(CASE WHEN STR_TO_DATE(pickTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_pickups,
    SUM(CASE WHEN STR_TO_DATE(dropTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(dropWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_deliveries
FROM otp_reports
WHERE mainShipment = 'YES'
  AND shipmentStatus = 'Complete'
GROUP BY clientName;
```

**Why `mainShipment = 'YES'`?**

Customers care about first pickup and final delivery, not intermediate legs. YES rows capture the customer-facing origin → destination with the relevant timestamps.

**Handling edge cases:**

1. **Missing `pickTimeArrived`**: Exclude from OTP calculation, but report these shipments separately
2. **Missing `dropTimeArrived`**: Exclude from OTD calculation, but report these shipments separately
3. **Orders with 0 YES rows**: Use fallback - first leg (earliest `pickTimeArrived`) for OTP, last leg (latest `dropTimeArrived`) for OTD

### 3.7 OTP/OTD for Carriers

**Rule:** Use `mainShipment = 'NO'` rows when available, fall back to `YES` rows for single-leg orders.

**Definitions:**
- **OTP (On Time Pickup):** `pickTimeArrived <= pickWindowFrom`
- **OTD (On Time Delivery):** `dropTimeArrived <= dropWindowFrom`

```sql
-- Carrier OTP/OTD using NO rows (for multi-leg orders)
SELECT
    carrierName,
    COUNT(*) as total_legs,
    SUM(CASE WHEN STR_TO_DATE(pickTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_pickups,
    SUM(CASE WHEN STR_TO_DATE(dropTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(dropWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_deliveries
FROM otp_reports
WHERE mainShipment = 'NO'
  AND shipmentStatus = 'Complete'
  AND carrierName IS NOT NULL AND carrierName != ''
GROUP BY carrierName;
```

**Why NO rows for carriers?**

Multi-leg orders have different carriers per leg. Each NO row represents a leg with its own carrier. Using YES rows would miss this granularity.

**Fallback for single-leg orders (~60%):**

For orders with 0 NO rows, use YES rows instead:

```sql
-- Carrier OTP/OTD using YES rows (for single-leg orders only)
SELECT
    carrierName,
    COUNT(*) as total_shipments,
    SUM(CASE WHEN STR_TO_DATE(pickTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_pickups,
    SUM(CASE WHEN STR_TO_DATE(dropTimeArrived, '%m/%d/%Y %H:%i:%s') <= STR_TO_DATE(dropWindowFrom, '%m/%d/%Y %H:%i:%s') THEN 1 ELSE 0 END) as on_time_deliveries
FROM otp_reports
WHERE mainShipment = 'YES'
  AND shipmentStatus = 'Complete'
  AND carrierName IS NOT NULL AND carrierName != ''
  AND orderCode IN (
      SELECT orderCode FROM otp_reports
      WHERE shipmentStatus = 'Complete'
      GROUP BY orderCode
      HAVING SUM(CASE WHEN mainShipment = 'NO' THEN 1 ELSE 0 END) = 0
  )
GROUP BY carrierName;
```

**Handling edge cases:**

1. **Missing `pickTimeArrived`**: Exclude from OTP calculation, report separately
2. **Missing `dropTimeArrived`**: Exclude from OTD calculation, report separately
3. **Crossdock legs** (`pickLocationName = dropLocationName`): Consider excluding - these are handling, not transport

---

## 4. Table Reference

### 4.1 orders Table

| Column | Description |
|--------|-------------|
| `code` | Order code (e.g., P-12345-2445) |
| `customerName` | Customer/client name |
| `revenueAllocation` | Order-level revenue (source of truth) |
| `costAllocation` | Order-level cost (source of truth) |
| `accessorialRevenue` | TONU charges (Truck Ordered Not Used) |
| `status` | Order status ('completed', 'canceled', 'created', 'inProgress') |
| `isCrossDock` | Cross-dock flag (1 = cross-dock, 0 = not cross-dock, NULL = unknown) |
| `scheduledPickupTime` | Scheduled pickup date (ISO 8601 format) |
| `actualPickupTime` | Actual pickup date (ISO 8601 format) |
| `scheduledDropoffTime` | Scheduled delivery date (ISO 8601 format) |
| `actualDropoffTime` | Actual delivery date (ISO 8601 format) |

### 4.2 otp_reports Table

*TODO: Document key columns*

---

## 5. SQL Examples

### Revenue Query (no date filter)
```sql
SELECT SUM(revenueAllocation) as total_revenue
FROM orders
WHERE customerName = 'DoorDash'
  AND (status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0));
```

### Profit Query with Date Range (cross-dock logic)
```sql
SELECT
    customerName,
    SUM(revenueAllocation) as total_revenue,
    SUM(costAllocation) as total_cost,
    SUM(revenueAllocation - costAllocation) as total_profit
FROM orders
WHERE customerName IN ('DoorDash', 'VFC - (DoorDash)')
  AND (status = 'completed' OR (status = 'canceled' AND accessorialRevenue > 0))
  AND (
    CASE
      WHEN isCrossDock = 0 AND actualDropoffTime IS NOT NULL AND actualDropoffTime != ''
        THEN SUBSTRING(actualDropoffTime, 1, 10)
      ELSE SUBSTRING(scheduledDropoffTime, 1, 10)
    END
  ) >= '2026-01-01'
  AND (
    CASE
      WHEN isCrossDock = 0 AND actualDropoffTime IS NOT NULL AND actualDropoffTime != ''
        THEN SUBSTRING(actualDropoffTime, 1, 10)
      ELSE SUBSTRING(scheduledDropoffTime, 1, 10)
    END
  ) <= '2026-01-04'
GROUP BY customerName;
```
⚠️ Note: The filter includes TONU charges (canceled orders with accessorialRevenue > 0)
⚠️ Note: Delivery date logic: cross-dock orders use scheduledDropoffTime, non-cross-dock use actualDropoffTime

### Shipment Count Query
```sql
SELECT COUNT(*) as shipments
FROM otp_reports
WHERE clientName = 'CookUnity Inc'
  AND mainShipment = 'YES'
  AND shipmentStatus = 'Complete'
  AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') >= '2026-01-01'
  AND STR_TO_DATE(pickWindowFrom, '%m/%d/%Y %H:%i:%s') < '2026-02-01';
```

### OTP Rate Query
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

---

## 5.5 Pallet / Parcel / Quantity Count

**Key Field:** `orders.shipmentType` determines the order type:
- `'LTL'` = Less Than Truckload (pallets)
- `'FTL'` = Full Truckload (pallets)
- `'PARCEL'` = Parcels

**Counting Rule:** 
```sql
SUM(pieces) WHERE mainShipment = 'YES'
```

**Why this works:**
- `mainShipment = 'YES'` rows represent actual customer shipments
- `mainShipment = 'NO'` rows are carrier/internal legs (ignore for quantity)
- SUM the pieces across all YES rows for the order

---

### Example - Total PALLETS for a customer:
```sql
SELECT 
    o.customerName,
    SUM(otp.pieces) as total_pallets
FROM orders o
JOIN otp_reports otp ON o.code = otp.orderCode
WHERE o.customerName = 'DoorDash'
  AND o.shipmentType = 'LTL'  -- FTL is full truck, pallet count not relevant
  AND otp.mainShipment = 'YES'
  AND (o.status = 'completed' OR (o.status = 'canceled' AND o.accessorialRevenue > 0))
GROUP BY o.customerName;
```

### Example - Total PARCELS for a customer:
```sql
SELECT 
    o.customerName,
    SUM(otp.pieces) as total_parcels
FROM orders o
JOIN otp_reports otp ON o.code = otp.orderCode
WHERE o.customerName = 'DoorDash'
  AND o.shipmentType = 'PARCEL'
  AND otp.mainShipment = 'YES'
  AND (o.status = 'completed' OR (o.status = 'canceled' AND o.accessorialRevenue > 0))
GROUP BY o.customerName;
```

### Example - Cost per pallet:
```sql
SELECT 
    o.customerName,
    SUM(o.costAllocation) as total_cost,
    SUM(otp.pieces) as total_pallets,
    SUM(o.costAllocation) / SUM(otp.pieces) as cost_per_pallet
FROM orders o
JOIN otp_reports otp ON o.code = otp.orderCode
WHERE o.customerName = 'DoorDash'
  AND o.shipmentType = 'LTL'  -- FTL is full truck, pallet count not relevant
  AND otp.mainShipment = 'YES'
  AND (o.status = 'completed' OR (o.status = 'canceled' AND o.accessorialRevenue > 0))
  AND otp.pieces > 0
GROUP BY o.customerName;
```

**Warning:** Exclude orders with `pieces = 0` or `NULL` from per-unit calculations.

---

## 6. Warnings & Gotchas

| Warning | Details |
|---------|---------|
| **profitNumber Column** | DO NOT USE - has data quality issues. Calculate as `revenueAllocation - costAllocation` |
| **orders Date Format** | ISO 8601 (e.g., `2024-11-14T15:15-06:00`). Use `SUBSTRING(field, 1, 10)` to extract date |
| **otp_reports Date Format** | `MM/DD/YYYY HH:MM:SS`. Use `STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')` |
| **DATE() Function** | DO NOT USE on orders table - converts to UTC first, causing late-evening orders to shift to next day |
| **TONU Charges** | Include canceled orders with `accessorialRevenue > 0` in revenue/profit calculations |
| **Cross-Dock Date Logic** | Non-cross-dock orders use actualDropoffTime; cross-dock orders use scheduledDropoffTime |
| **otp_reports Revenue** | Inconsistent across clients - use `orders` table instead |
| **Status Values** | `orders` table uses lowercase ('completed', 'canceled'), `otp_reports` uses title case ('Complete') |

---

## 7. Appendix

### 7.1 Verification Notes

**Revenue/Cost (Verified 2026-02-21)**:
- Tested across LTL Direct, LTL Multi-leg, FTL Multidrop, FTL Multistop scenarios
- Confirmed `orders.revenueAllocation` matches expected values
- Confirmed `otp_reports` sum varies by client (some double-count, some don't)
- Conclusion: `orders` table is the only reliable source

