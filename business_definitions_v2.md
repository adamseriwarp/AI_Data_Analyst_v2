# Warp Data Analyst - Business Definitions v2

This document provides the AI Data Analyst with verified business logic for answering data questions.

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
```

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
WHERE status = 'Complete'  -- or appropriate status filter
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

**Rule:** Always ask the user which date field to filter on.

There are three date options for filtering shipments:

| Field | Meaning | Use When |
|-------|---------|----------|
| `pickWindowFrom` | When pickup was **scheduled** | Analyzing planned/booked shipments |
| `pickTimeArrived` | When driver **arrived** at pickup | Analyzing actual pickup timing |
| `pickTimeDeparted` | When driver **departed** from pickup | Analyzing when shipments left origin |

**Example prompt to user:**
> "How would you like to filter by date?
> 1. **Scheduled pickup date** (when the pickup was planned)
> 2. **Actual arrival date** (when the driver arrived)
> 3. **Actual departure date** (when the driver left with the shipment)"

**Note:** These fields are in `otp_reports` table. Use `STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')` for date parsing.

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
| `status` | Order status |

### 4.2 otp_reports Table

*TODO: Document key columns*

---

## 5. Warnings & Gotchas

| Warning | Details |
|---------|---------|
| **profitNumber Column** | DO NOT USE - has data quality issues. Calculate as `revenueAllocation - costAllocation` |
| **Date Format** | Most dates are `MM/DD/YYYY HH:MM:SS`. Use `STR_TO_DATE(field, '%m/%d/%Y %H:%i:%s')` |
| **otp_reports Revenue** | Inconsistent across clients - use `orders` table instead |

---

## 6. Appendix

### 6.1 Verification Notes

**Revenue/Cost (Verified 2026-02-21)**:
- Tested across LTL Direct, LTL Multi-leg, FTL Multidrop, FTL Multistop scenarios
- Confirmed `orders.revenueAllocation` matches expected values
- Confirmed `otp_reports` sum varies by client (some double-count, some don't)
- Conclusion: `orders` table is the only reliable source

