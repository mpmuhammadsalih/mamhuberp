# Nexa Mobile API — database objects

This backend uses **Oracle** with two conceptual layers:

| Where (`.env`) | Oracle user | Tables this repo expects | What the mobile app uses them for |
|----------------|-------------|--------------------------|-----------------------------------|
| **Auth / catalogue DB** | `ORACLE_USER` / `ORACLE_DSN` (see `.env`) | `LOGIN_USERS`, `ROLE_PERMISSIONS`, `TENANT_DATABASES` | Login, JWT, RBAC menus/permissions, which tenant DB to open |
| **Tenant ERP DB(s)** | One connection per row in `TENANT_DATABASES` (`IP`/`PORT`/`SERVICE_NAME`/credentials) | `ITEMMASTER`, `CUSTOMER`, `BILLHDR`, purchase GRN tables, etc. — **your existing ERP schema** | Inventory, dashboards, purchase/GRN, sales — code reads tables that already exist |
| **Tenant ERP DB — optional extension** | Same tenant schema | `GRN_MOBILE_LINE_EXT` | Extra GRN line fields used by the mobile GRN wizard; see `install_grn_mobile_line_ext_oracle_complete.sql` |

Stock counting uses the **tenant** schema:

| Table | Read / write | Purpose |
|-------|----------------|---------|
| **`ITEMMASTER`** | Read | Item list + system on-hand qty |
| **`STOCK_COUNT_HDR`** | Write | Count session header (`COUNT_NO`, `LOCATIONCODE`, `STATUS` = DRAFT/POSTED, …) |
| **`STOCK_COUNT_DTL`** | Write | Count lines (`ITEMCODE`, `WAREHOUSE_ID`, `SYSTEM_QTY`, `COUNTED_QTY`, `VARIANCE_QTY`, optional `OLD_RETAIL_PRICE`, `NEW_RETAIL_PRICE`, …) |
| **`STOCK_COUNT_PRICE_HDR`** | Write | Retail price update header (`BATCH_NO` links to detail rows) |
| **`STOCK_COUNT_PRICE_UPDATE`** | Write | Pending retail price lines per item (`BATCH_NO` = header batch; applied on POST) |

Mobile API: `POST/GET /api/v1/stock-count/sessions`, `PUT .../lines`, `POST .../post`. Run [`install_stock_count_price_update_oracle.sql`](./install_stock_count_price_update_oracle.sql) on each tenant for retail price capture. Core count tables must already exist in Oracle.

---

## What you should do (order)

1. **Auth database** (`ORACLE_*` in `.env`): run  
   [`install_nexa_mobile_auth_schema_oracle.sql`](./install_nexa_mobile_auth_schema_oracle.sql)  
   Connect as the same user the API uses (`ORACLE_USER`).

2. **Insert tenants**: add rows to `TENANT_DATABASES` with each company’s ERP DB connectivity (`IP`, `PORT`, `SERVICE_NAME`, Oracle `USERNAME`, `PASSWORD`).

3. **Insert users**: add rows to **`LOGIN_USERS`**. Passwords must be **Werkzeug** hashes (`pbkdf2:sha256:...` or `scrypt:...`). Generate with Python (inside your venv that has `werkzeug`):

   ```bash
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YourPlainPassword'))"
   ```

4. **Insert RBAC**: add rows to **`ROLE_PERMISSIONS`** linking each `ROLE_ID` to permission keys. Minimum keys used by routes today include:

   - `dashboard.dashboard`
   - `itemmaster.productlist` (inventory / stock counting)
   - `purchase.purchase_order_list`
   - `purchase.purchase_order_add`
   - `sales.sales_invoice`
   - `accounts.customer_ledger_page`

   Users `admin` / `super` bypass permission checks for RBAC (`deps_auth.require_permission`), but still need valid rows in **`LOGIN_USERS`**.

5. **Tenant ERP DB**: ensure `ITEMMASTER` (and supporting columns used by queries) exists; no script in this repo creates core ERP masters.

6. **Optional GRN extension**: run `install_grn_mobile_line_ext_oracle_complete.sql` on **each tenant** schema where you use the mobile GRN flow.

7. **Stock count retail prices**: run `install_stock_count_price_update_oracle.sql` on **each tenant** where mobile users update retail price during counting.

8. **Mobile tenant setup (optional)**: set `CONFIG_SETUP_KEY` in `erp_api/.env`. In the app **Server & database** screen, enter ERP host/port/service/user/password and save to `TENANT_DATABASES` (same key in **Setup key** field).

---

## Config flags that touch DDL automatically

| Flag | Effect |
|------|--------|
| `AUTO_CREATE_GRN_MOBILE_EXT` | If true, API may attempt to create `GRN_MOBILE_LINE_EXT` at runtime (needs `CREATE TABLE` on tenant user). Prefer running the SQL file manually instead. |

---

## Files

| Script | Purpose |
|--------|---------|
| `install_nexa_mobile_auth_schema_oracle.sql` | Creates `LOGIN_USERS`, `ROLE_PERMISSIONS`, `TENANT_DATABASES` if missing |
| `install_grn_mobile_line_ext_oracle_complete.sql` | Tenant-side GRN mobile extension |
| `install_stock_count_price_update_oracle.sql` | `STOCK_COUNT_PRICE_HDR`, `STOCK_COUNT_PRICE_UPDATE` + DTL retail columns |
| `add_lpohdr_nexa_grn_status_oracle.sql` | Existing optional ERP column patch (GRN/Nexa hub) |

If you renamed objects in production, adapt the DDL or synonyms before running.
