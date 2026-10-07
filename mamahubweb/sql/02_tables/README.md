# Table scripts

## Safe to run (create-if-missing)

- `01_company_branch_warehouse.sql` — skipped if tables already exist
- `02_user_role_permission.sql` — skipped if tables already exist
- `06_mh_ecommerce_extensions.sql` — **preferred** new ecommerce tables (`MH_*`)

## Do not run against this shared DB

These conflict with ERP-owned objects and are excluded from `apply_schema.py`:

- `03_category_brand_age_group.sql` — ERP already owns `CATEGORY`
- `04_product_and_image.sql` — use `ITEMMASTER` / `PRODUCT_IMAGES`
- `05_inventory_balance.sql` — use `WAREHOUSE_STOCK`

Never drop existing tables.
