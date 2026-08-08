# Send SMS – Customers with Outstanding: How Data Is Taken

## 1. Where this is used

- **Page:** Send SMS (`/sms` or equivalent route).
- **Section:** “Customers with Outstanding” table (customer list with Outstanding Amount, Collection, etc.).
- **Backend:** `get_cash_customers_with_outstanding(date_from, date_to)` in `blueprints/sms.py`.

---

## 2. Who is shown (list of customers)

A customer appears in the list if **either** of the following is true:

### 2.1 From **tblsettlement** (main source)

- **Table:** `tblsettlement` (alias `ts`).
- **Conditions:**
  - `ts.balance > 0` (or equivalent: BALANCE / OUTSTANDING / NETBALANCE).
  - `ts.flag = 'B'` (bill/outstanding rows, not receipts).
- **No invoice-code filter:** All customers are included (not restricted to invoicecode = 1). Customer table is joined only for **name, phone, etc.**

So: **“Customers with outstanding”** = rows in **tblsettlement** with balance > 0 and flag = 'B' (**all customers**).

### 2.2 From **tbltempsettlement** (extra rows when dates are set)

- **Table:** `tbltempsettlement` (collection / receipts).
- **When:** Only when **From Date** and **To Date** are both provided on the page.
- **Logic:** Include customers who have **collection** in that date range (e.g. `flag = 'R'`, paidate between From/To) but who do **not** appear in the tblsettlement-based list above (i.e. they have no outstanding in tblsettlement).
- **Effect:** Such customers are shown with **invoicecount = 0**, **lastbilldate = NULL**, **outstandingamount = 0**, and only **collectionamount** (and optionally pending) filled later.

So the **list of rows** is:  
**tblsettlement (balance > 0, flag = 'B', cash only)** ∪ **tbltempsettlement (collection in date range, not in tblsettlement list)**.

---

## 3. Where each column gets its data

| Column              | Source |
|---------------------|--------|
| **customercode**    | `tblsettlement.customercode` (or customer table if joined); same for UNION part from `tbltempsettlement.customercode`. |
| **customername**    | **Customer table** (CUSTOMER/CUSTOMERS): name column (e.g. CUSTOMERNAME, CUST_NAME). |
| **address**         | **Customer table**: address column. |
| **phoneno / whatsappno** | **Customer table**: MOBILE/PHONE/WHATSAPP, etc. |
| **invoicecount**    | **tblsettlement only**: COUNT(DISTINCT billno) for that customer (flag='B', balance > 0). |
| **lastbilldate**    | **tblsettlement only**: MAX(billdate) for that customer. |
| **outstandingamount** | **tblsettlement only**: SUM(balance) where balance > 0 and flag = 'B'. |
| **collectionamount** | **tbltempsettlement**: SUM(paidamount) where flag = 'R' and paidate between From Date and To Date (date filter from the page). |
| **pendingamount**   | **BILLHDR** (if used): SUM(netbillamount) where billtype = 'T' and billdate in the selected date range. Optional; not used for “who is in the list”. |

- **Outstanding** (who has balance and how much) comes only from **tblsettlement**.
- **Customer name and contact** come only from the **customer** table.
- **Collection** comes from **tbltempsettlement** and is filtered by the page’s date range.
- **Pending** (if shown) comes from **BILLHDR** and is also date-filtered.

---

## 4. Date filters

- **From Date / To Date** on the page:
  - **Do not** filter tblsettlement: outstanding and invoice count are **all time** (all outstanding bills for that customer).
  - **Do** filter **tbltempsettlement** for **collectionamount** (paidate between From and To).
  - **Do** filter **BILLHDR** for **pendingamount** (billdate between From and To), when pending is used.
- The UNION that adds “collection-only” customers runs only when **both** From Date and To Date are provided.

---

## 5. Summary

- **“Customers with outstanding”** = customers with **tblsettlement** rows (balance > 0, flag = 'B'); plus (when dates are set) customers who have **tbltempsettlement** collection in that range but no outstanding in tblsettlement. **All customers** (no invoicecode restriction).
- **Outstanding amount and invoice count** = from **tblsettlement** only.
- **Customer name, phone, address** = from **customer** table only.
- **Collection amount** = from **tbltempsettlement** (date-filtered).
- **Pending amount** = from **BILLHDR** (date-filtered), if available.
- **No BILLHDR** is used to decide who has outstanding; that comes from **tblsettlement** only. Customer table is used only for name/phone. No invoicecode filter.
