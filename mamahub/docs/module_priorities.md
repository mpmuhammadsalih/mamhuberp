# Module Priorities

## Priority 1: Foundation

- Addons: `auth`, `api`, `dashboard`, `roles`, `users`, `tenants`
- Reason: every migrated page needs authenticated user context, tenant/location scope, and menu permissions.
- New API: `/api/v1/auth/*`, `/api/v1/navigation/*`, `/api/v1/health`

## Priority 2: Master Data

- Addons: `customer`, `customer_category`, `salesman`, `route_master`, `session_master`, `employee`, `supplier`, `company_profile`, `branch_location`, `gl_dimension`, `system_config`
- Reason: low-risk CRUD screens establish reusable form/list patterns and feed transaction screens.

## Priority 3: Inventory and Warehouse

- Addons: `itemmaster`, `warehouse`, `barcode_management`, `menu_price_setup`, `promotions`
- Reason: item, UOM, warehouse, barcode, and stock data are dependencies for sales, POS, purchase, reports, and accounts.

## Priority 4: Transactions

- Addons: `sales`, `pos_billing`, `purchase`
- Reason: highest business risk and largest route modules. These should be migrated after lookup and master APIs are stable.

## Priority 5: Finance and Reports

- Addons: `accounts`, `reports`, `sales_summary`, `salesman_summary`, `temporary_collection`, `temporary_pending`, `temporary_invoices`
- Reason: these depend on transaction data and need reusable filters, exports, PDFs, and permission checks.

## Priority 6: HO, Collaboration, Utilities

- Addons: `ho`, `tasveek`, `chat`, `sms`, `notifications`, `activity_log`, `db_sync`, `utilities_db_modes`, `demo_sales`
- Reason: specialized workflows can reuse the finalized shell, auth, export, and CRUD patterns.

