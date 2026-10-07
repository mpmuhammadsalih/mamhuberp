# Salesman Outstanding Details – How the report fetches data

## 1. How you open the report

- **URL:** `/reports/salesman-outstanding/details?bucket=all&salesman_code=39`
- **Query params:**
  - `bucket`: `all` | `30` | `60` | `90` | `120` | `120p`
  - `salesman_code`: e.g. `39` (the salesman you select)

The route calls `get_salesman_outstanding_details(salesman_code, bucket)` in `db.py`.

---

## 2. Where the data comes from

The report shows **one row per outstanding invoice** (balance > 0). **Details come only from tblsettlement**; **BILLHDR is not used**. For customer name, the **customer table** is joined (no other header table). Salesman is from **tblsettlement** only. All customers included (no invoice-code filter).

### 2.1 Base table: `tblsettlement` (alias `s`)

- **Used columns (detected by name):**
  - Bill number: `BILLNO` / `BILL_NO` / `billno`
  - Bill date: `BILLDATE` / `BILL_DATE` / `billdate`
  - Customer: `CUSTOMERCODE` / `CUSTOMER_CODE` / `customercode`
  - Balance: `BALANCE` / `OUTSTANDING` / `NETBALANCE`
  - Flag: `FLAG` / `FLAG_CODE` / `flag`
  - Amounts: `BILLAMOUNT`, `PAIDAMOUNT` (or equivalents)
  - Salesman (if present): `SALESMANCODE` / `SALESMAN_CODE` / `salesmancode` / `salesman`

- **Row must satisfy:**
  - `s.flag = 'B'` (bill/outstanding, not receipt)
  - `NVL(s.balance, 0) <> 0` (balance > 0)

So only **outstanding bills** in `tblsettlement` (flag = 'B', balance > 0) are considered.

---

### 2.2 Salesman (tblsettlement only, no BILLHDR)

- **If tblsettlement has a salesman column:** salesman is taken from `s.<salesmancode_col>`, and when a salesman is selected we filter `AND s.<salesmancode_col> = :salesman_code`.
- **Else:** no salesman column is used; salesmancode/salesmanname are NULL and no salesman filter is applied.

**BILLHDR is not used** for this report.

---

### 2.3 Join to customer table (alias `c`) – customer name only

- **Join:** `LEFT JOIN customers c ON s.customercode = c.<code_col>`
- **Table:** First existing of `customers`, `CUSTOMERS`, `CUSTOMER`, `customer`.
- **No invoice-code filter:** All customers are included; invoice code = 1 is not required.


---

### 2.4 Bucket (date filter)

- **Bucket = All:** No extra date condition.
- **30 / 60 / 90 / 120 / 120p:** Extra condition on **invoice date** (from `tblsettlement`, e.g. `s.billdate`) vs `SYSDATE` (e.g. 0–30 days, 31–60, etc.).

Date column is resolved by `_resolve_invoice_date_column()` (default `billdate`), or env `DASH_INVOICE_DATE_COLUMN`.

---

## 3. Summary: a row appears only if

1. It is in **tblsettlement** with **flag = 'B'** and **balance > 0**.
2. When a salesman is selected: **salesman** = selected code from **tblsettlement** only (if tblsettlement has a salesman column).
3. All customers are included (no invoice-code filter).
4. If bucket is not “All”, the **invoice date** falls in the chosen aging bucket.

**BILLHDR is not used.**

---

## 4. Why you might see “No invoice details found”

1. **No rows with balance > 0**
   - **Check:**  
     `SELECT * FROM tblsettlement WHERE flag = 'B' AND NVL(balance, 0) <> 0` (or your balance column name).

2. **Salesman filter**
   - When you select a salesman (e.g. 39), rows must have that salesman in **tblsettlement.salesmancode** (or your salesman column name). The customer table is not used for salesman.
   - **Check:**  
     `SELECT * FROM tblsettlement WHERE flag = 'B' AND balance <> 0 AND salesmancode = '39'` (use your column name if different).

3. **Column/table names**
   - If your DB uses different table or column names, the app’s detection might not find them.
   - **Check:**  
     Enable debug (see below) and compare the logged query with your actual table/column names.

---

## 5. Debug: log the actual SQL

Set in your environment (or `.env`):

```bash
DEBUG_SALESMAN_OUTSTANDING=1
```

Then run the report again (e.g. Salesman 39, All Periods). In the app logs you should see the **exact SELECT** and **bindings** used. Compare that SQL with your tables (tblsettlement, BILLHDR, customers) to see which condition removes the rows.

---

## 6. Quick DB checks (Oracle)

```sql
-- Outstanding rows in tblsettlement (sample) – balance > 0, flag = 'B'
SELECT s.billno, s.customercode, s.balance, s.flag, s.salesmancode   -- if salesman column exists
FROM tblsettlement s
WHERE s.flag = 'B' AND NVL(s.balance, 0) <> 0
AND ROWNUM <= 10;

-- Customer names for those outstanding
SELECT c.cust_code, c.customername
FROM customers c
WHERE c.cust_code IN (SELECT customercode FROM tblsettlement WHERE flag = 'B' AND balance <> 0 AND ROWNUM <= 20);
```

Replace `billno`, `salesmancode`, `cust_code`, `customername` with your actual column names if different.
