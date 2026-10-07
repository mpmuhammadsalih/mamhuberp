# Sales Summary - How It Is Generated

## Overview

The Sales Summary page (`/sales-summary`) generates a summary of sales data for a selected date range. It shows various sales metrics and calculated totals.

---

## 1. Data Flow

1. **User selects date range** (From Date, To Date) and clicks "Load"
2. **Route handler** (`sales_summary()` in `blueprints/sales_summary.py`) receives the request
3. **Two main functions are called:**
   - `_fetch_summary_details(date_from, date_to)` - Gets the detailed breakdown
   - `_calculate_totals(date_from, date_to)` - Calculates totals, target, percentage, margin
4. **Deduction is calculated** from summary details (in the route handler)
5. **Template renders** the data

---

## 2. Summary Details (`_fetch_summary_details`)

This function builds a **UNION ALL query** combining multiple sub-queries, each returning a `description` and `amount`. All queries filter by the date range (`billdate BETWEEN date_from AND date_to + 1`).

### 2.1 Main Tables Used

- **BILLHDR** / **billhdr** - Main bill header table (required)
- **FINALSALE** / **finalsale** - Final sale summary table
- **DRHDR** / **drhdr** - Debit note header table
- **CUSTOMER** / **CUSTOMERS** - Customer master table
- **BILLDTL** / **billdtl** - Bill detail/line items table
- **ITEMMASTER** / **itemmaster** - Item master table
- **TBLCOMMISSIONREMOVEDCATEGORY** - Commission categories table

### 2.2 Summary Items Generated

Each item below becomes one row in the "Summary Details" table:

#### 1. **SALES IN SYSTEM**
- **Source:** `BILLHDR`
- **Calculation:** `SUM(netbillamount + redemption)` (or just `SUM(netbillamount)` if no redemption column)
- **Date filter:** Bill date in range

#### 2. **NUMBER OF INVOICES**
- **Source:** `BILLHDR`
- **Calculation:** `COUNT(billno)`
- **Date filter:** Bill date in range

#### 3. **REDEMPTION AMOUNT**
- **Source:** `BILLHDR`
- **Calculation:** `SUM(redemption)` (if redemption column exists)
- **Date filter:** Bill date in range

#### 4. **TRANSFER SALE** (by Customer Name)
- **Source:** `BILLHDR` + `CUSTOMER` (join)
- **Calculation:** `SUM(netbillamount)` grouped by customer name
- **Filter:** Customer has `transferbranch = 'Y'`
- **Date filter:** Bill date in range
- **Note:** One row per transfer customer

#### 5. **CIGARETTES SALE**
- **Source:** `BILLDTL` + `BILLHDR` + `ITEMMASTER` + `TBLCOMMISSIONREMOVEDCATEGORY`
- **Calculation:** `SUM(qty * rate)` for items whose category is in commission table
- **Filter:** Excludes transfer branch customers (`transferbranch != 'Y'`)
- **Date filter:** Bill date in range

#### 6. **COST TO COST**
- **Source:** `BILLDTL` + `BILLHDR`
- **Calculation:** `SUM(qty * rate)` where `rate = cost`
- **Formula:** For each line item where selling rate equals cost price, calculate `qty × rate`, then sum all such amounts
- **Meaning:** Total sales value of items sold at cost price (zero margin - no profit, no loss)
- **Filter:** 
  - Excludes transfer branch customers (`transferbranch != 'Y'`)
  - Only includes items where `rate = cost` (selling rate equals cost price)
- **Date filter:** Bill date in range
- **Example:** If Item A: Qty=10, Rate=100, Cost=100 → Amount = 1000. If Item B: Qty=5, Rate=120, Cost=100 → Not included (rate ≠ cost). COST TO COST = Sum of all items where rate = cost.

#### 7. **BELOW COST**
- **Source:** `BILLDTL` + `BILLHDR`
- **Calculation:** `SUM(qty * (rate - cost)) * -1` where `rate < cost` and `qty > 0`
- **Filter:** Excludes transfer branch customers
- **Date filter:** Bill date in range
- **Note:** Amount is negative (loss), so multiplied by -1

#### 8. **TOTAL DISCOUNT**
- **Source:** `FINALSALE`
- **Calculation:** `SUM(totaldiscount)`
- **Date filter:** Bill date in range

#### 9. **TOTAL ROUND OFF**
- **Source:** `FINALSALE`
- **Calculation:** `SUM(roundoff)`
- **Date filter:** Bill date in range

#### 10. **TOTAL DEBIT NOTE**
- **Source:** `DRHDR`
- **Calculation:** `SUM(dramount)`
- **Date filter:** DR date in range

#### 11. **NET SALE**
- **Source:** `FINALSALE`
- **Calculation:** `SUM(netbillamount)`
- **Date filter:** Bill date in range

#### 12. **TRANSFER SALE** (summary)
- **Source:** `BILLHDR` + `CUSTOMER` (join)
- **Calculation:** `SUM(netbillamount)` for all transfer customers combined
- **Filter:** Customer has `transferbranch = 'Y'`
- **Date filter:** Bill date in range

#### 13. **SALE RETURN**
- **Source:** `BILLHDR`
- **Calculation:** `SUM(netbillamount + redemption)` where `netbillamount < 0`
- **Date filter:** Bill date in range
- **Note:** Only negative amounts (returns)

---

## 3. Calculated Totals (`_calculate_totals`)

### 3.1 Total Sale
- **Source:** `BILLHDR`
- **Calculation:** `SUM(netbillamount + redemption)` (or just `SUM(netbillamount)`)
- **Date filter:** Bill date in range

### 3.2 Deduction
- **Calculated in route handler** (not in `_calculate_totals`)
- **Source:** Sum of specific items from Summary Details:
  - TRANSFER SALE (summary)
  - REDEMPTION AMOUNT
  - CIGARETTES SALE
  - **COST TO COST** - Items sold at cost price (rate = cost), zero margin sales
  - BELOW COST (absolute value, as it's already negative)
- **Formula:** Sum of amounts for these descriptions
- **Why COST TO COST is deducted:** Items sold at cost price have zero margin, so they reduce the effective net sale (no profit from these sales)

### 3.3 Net Sale
- **Calculation:** `Total Sale - Deduction`

### 3.4 Target
- **Source:** `TBLTARGETMONTHLY` / `tbltargetmonthly`
- **Filter:** Year and Month matching the `date_from` month
- **Column:** `AMOUNT` / `TARGET` / `TARGETAMOUNT`

### 3.5 Percentage
- **Calculation:** `(Net Sale / Target) * 100`
- **If Target = 0:** Percentage = 0

### 3.6 Margin
- **Source:** `FINALSALE`
- **Calculation:** `((SUM(netbillamount) - SUM(billdtlcost)) / SUM(netbillamount)) * 100`
- **Filter:** `netbillamount > 0` and date in range
- **Formula:** `(Revenue - Cost) / Revenue * 100`

---

## 4. Date Range Filtering

All queries use:
```sql
WHERE billdate BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD') 
  AND TO_DATE(:date_to, 'YYYY-MM-DD') + 1
```

The `+ 1` ensures the "To Date" is inclusive (includes the entire day).

---

## 5. Key Points

- **Multiple tables:** Data comes from BILLHDR, FINALSALE, DRHDR, BILLDTL, CUSTOMER, etc.
- **UNION ALL:** Summary details are combined using UNION ALL (allows duplicates if needed)
- **Transfer customers:** Many calculations exclude customers with `transferbranch = 'Y'`
- **Deduction calculation:** Happens in the route handler by summing specific summary items
- **Column detection:** The code auto-detects column names (e.g., `BILLDATE` vs `BILL_DATE`)
- **Error handling:** If a table/column is missing, that item is skipped (not all items are required)

---

## 6. Example Flow

1. User selects: From Date = `2026-01-01`, To Date = `2026-01-31`
2. `_fetch_summary_details` builds 13 UNION ALL queries
3. Executes combined query, returns rows like:
   - `{description: "SALES IN SYSTEM", amount: 100000}`
   - `{description: "NUMBER OF INVOICES", amount: 500}`
   - `{description: "TRANSFER SALE", amount: 5000}`
   - etc.
4. `_calculate_totals` calculates:
   - Total Sale = 100000
   - Target = 120000 (from TBLTARGETMONTHLY)
   - Margin = 25% (from FINALSALE)
5. Route handler calculates:
   - Deduction = 5000 (TRANSFER SALE) + 1000 (REDEMPTION) + ... = 6000
   - Net Sale = 100000 - 6000 = 94000
   - Percentage = (94000 / 120000) * 100 = 78.33%
6. Template displays all summary details and calculated totals

---

## 7. Files Involved

- **Route:** `blueprints/sales_summary.py` → `sales_summary()` function
- **Data functions:** `_fetch_summary_details()`, `_calculate_totals()`
- **Template:** `templates/sales_summary.html`
- **Database:** Multiple tables (BILLHDR, FINALSALE, DRHDR, etc.)
