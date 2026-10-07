# Oracle schema policy (shared Dynamics / MAMAHUB DB)

## Rules

1. **Never DROP, TRUNCATE, or DELETE** existing database objects or business data.
2. **Prefer existing ERP tables** (`ITEMMASTER`, `CUSTOMER`, `CATEGORY`, `WAREHOUSE_STOCK`, `PRODUCT_IMAGES`, etc.).
3. **Create only missing e-commerce tables** with non-colliding names (prefer `MH_` prefix).
4. Schema apply is **create-if-missing only** via `scripts/apply_schema.py`.

## What was introduced by Phase 1/2 attempt

### Sequences created (MamaHub naming)

These sequences exist and will be left in place (no drop):

- `SEQ_COMPANY_ID`, `SEQ_BRANCH_ID`, `SEQ_WAREHOUSE_ID`
- `SEQ_USER_ID`, `SEQ_ROLE_ID`, `SEQ_PERMISSION_ID`, `SEQ_USER_ROLE_ID`, `SEQ_ROLE_PERMISSION_ID`
- `SEQ_CATEGORY_ID`, `SEQ_BRAND_ID`, `SEQ_AGE_GROUP_ID`
- `SEQ_PRODUCT_ID`, `SEQ_PRODUCT_IMAGE_ID`, `SEQ_INVENTORY_BALANCE_ID`
- `SEQ_CUSTOMER_ID`, `SEQ_ORDER_ID`, `SEQ_ORDER_ITEM_ID`

### Tables with overlapping names

These names already exist in `MAMAHUB`. Do **not** recreate or replace them:

| Name | Reality |
|------|---------|
| `COMPANY`, `BRANCH`, `WAREHOUSE` | Present (ecommerce-style columns) |
| `APP_USER`, `ROLE`, `PERMISSION`, `USER_ROLE`, `ROLE_PERMISSION` | Present |
| `CATEGORY` | **ERP polymorphic master** — `FLAG` = M/D/C/B/Z/L (see Nexus_Cloud) |
| `ITEMMASTER` | Real product master |
| `CUSTOMER` | Real customer master |
| `PRODUCT_IMAGES` | Existing product images |
| `WAREHOUSE_STOCK` | Existing stock by warehouse |

### Not created (safe to create later with MH_ names if needed)

- `AGE_GROUP`, `BRAND`, `PRODUCT`, `PRODUCT_IMAGE`, `INVENTORY_BALANCE`

## Target mapping for the e-commerce API

| Domain | Use existing | Create only if required |
|--------|--------------|-------------------------|
| Products | `ITEMMASTER` | `MH_PRODUCT_EXT` (optional ecommerce fields) |
| Product images | `PRODUCT_IMAGES` | — |
| Categories | `CATEGORY` (M→D→C via `ID` = parent `CODE`) | `MH_AGE_GROUP`, `MH_INTEREST` |
| Brands | `CATEGORY` where `FLAG='B'` + `ITEMMASTER.BRANDCODE` | `MH_BRAND` (web marketing overlay only) |
| Customers | `CUSTOMER` | auth/profile extension table if needed |
| Stock | `WAREHOUSE_STOCK`, `ITEMMASTER.CURRENTSTOCK` | `MH_INVENTORY_RESERVATION` |
| Org | `COMPANY`, `BRANCH`, `WAREHOUSE` / `WAREHOUSE_MASTER` | — |
| Users/RBAC | `APP_USER` / `LOGIN_USERS` / `ROLE*` | only missing permission rows via insert-if-absent |

**Nexus reference:** `docs/NEXUS_ERP_REFERENCE.md` and `D:\webapps\Nexus_Cloud\db\itemmaster_detail_select.py`

## Disabled scripts

- `sql/99_drop/*` is disabled and must not be executed.
