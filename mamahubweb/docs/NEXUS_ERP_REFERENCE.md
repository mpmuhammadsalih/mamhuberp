# Nexus_Cloud ERP Reference (for MamaHub)

MamaHub shares the same Oracle schema as **Nexus_Cloud** (`MAMAHUB` user on `dynamics`).
This document describes how Nexus uses ERP tables so MamaHub follows the same patterns.

**Reference project:** `D:\webapps\Nexus_Cloud`

---

## Core idea

Nexus does **not** use separate product/category/brand tables for ERP data.
Everything comes from:

| Domain | Table | Notes |
|--------|-------|-------|
| Products | `ITEMMASTER` | PK: `(LOCATIONCODE, ITEMCODE)` |
| Categories & brands | `CATEGORY` | One table, `FLAG` column discriminates type |
| Stock | `ITEMMASTER.CURRENTSTOCK` + `WAREHOUSE_STOCK` | Branch/warehouse qty |
| Images | `PRODUCT_IMAGES` | Schema exists; Nexus barely uses it |
| Customers | `CUSTOMER` | Separate from product `CATEGORY` |

MamaHub **`MH_*` tables** (e.g. `MH_AGE_GROUP`, `MH_BRAND`) are **e-commerce extras only**.
Real catalog data must come from ERP tables like Nexus.

---

## CATEGORY — one table, many roles (`FLAG`)

| FLAG | Meaning | Parent link |
|------|---------|-------------|
| `M` | Main category | — |
| `D` | Department / category level | `ID` = parent **M.CODE** |
| `C` | Micro-category (subcategory) | `ID` = parent **D.CODE** |
| `B` | **Brand** | flat lookup (`ID` = own `CODE`) |
| `Z` | Size | flat lookup |
| `L` | Color | flat lookup |

Hierarchy:

```text
Main (M)
 └── Department (D)     WHERE FLAG='D' AND ID = M.CODE
      └── Micro (C)     WHERE FLAG='C' AND ID = D.CODE
```

**Nexus helpers:** `get_categories()`, `get_category_master_tree()`, `get_departments_by_maincategory_code()`, `get_categories_by_department_code()` in `Nexus_Cloud/db/__init__.py`.

---

## ITEMMASTER — how products link to category & brand

| ITEMMASTER column | Points to |
|-------------------|-----------|
| `MAINCATEGORY` | `CATEGORY` where `FLAG='M'` |
| `DEPARTMENTCODE` | `CATEGORY` where `FLAG='D'` |
| `CATEGORYCODE` | `CATEGORY` where `FLAG='C'` (micro — used in product filters) |
| `BRANDCODE` | `CATEGORY` where `FLAG='B'` (**brand is not a separate table**) |
| `SIZECODE` | `CATEGORY` where `FLAG='Z'` |
| `COLORCODE` | `CATEGORY` where `FLAG='L'` |

**Important:** Product list filters in Nexus use `CATEGORYCODE` (micro `C`) and `BRANDCODE`, scoped by `LOCATIONCODE`.

---

## Canonical JOIN pattern (from Nexus)

File: `Nexus_Cloud/db/itemmaster_detail_select.py`

```sql
FROM ITEMMASTER im
LEFT JOIN CATEGORY cat_m
       ON cat_m.FLAG = 'M' AND cat_m.CODE = im.MAINCATEGORY AND cat_m.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_d
       ON cat_d.FLAG = 'D' AND cat_d.CODE = im.DEPARTMENTCODE AND cat_d.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_c
       ON cat_c.FLAG = 'C' AND cat_c.CODE = im.CATEGORYCODE AND cat_c.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_b
       ON cat_b.FLAG = 'B' AND cat_b.CODE = im.BRANDCODE AND cat_b.LOCATIONCODE = im.LOCATIONCODE
```

MamaHub equivalent: `backend/app/repositories/itemmaster_queries.py`

---

## Product listing & search (Nexus API pattern)

**Route:** `GET /productlist/api/items`  
**File:** `Nexus_Cloud/addons/itemmaster/controllers/routes.py`

**Query params → SQL filters:**

| Param | Filter |
|-------|--------|
| `search` | `ITEMCODE`, `MANUFACTURERID`, `ITEMNAME` (LIKE) |
| `brandCode` | `im.BRANDCODE` |
| `categoryCode` | `im.CATEGORYCODE` (micro category) |
| `supplierCode` | `im.SUPCODE` |
| `stockFilter` | `CURRENTSTOCK` notzero / greater / less |
| `page`, `per_page` | ROWNUM pagination |

**Backend:** `get_items_list()` in `Nexus_Cloud/db/__init__.py` (~L19575)

Brand/category names resolved via scalar subqueries:

```sql
(SELECT NVL(MAX(brand.NAME), '') FROM CATEGORY brand
 WHERE brand.CODE = im.BRANDCODE AND brand.FLAG = 'B') AS BRANDNAME
```

---

## Stock

1. **`ITEMMASTER.CURRENTSTOCK`** — branch total (product list, KPIs)
2. **`WAREHOUSE_STOCK`** — `(LOCATIONCODE, WAREHOUSE_ID, ITEMCODE, QTY)`
3. Legacy **`STORE1`…`STORE10`** on ITEMMASTER (fallback)

Sales popup uses `GREATEST(warehouse_sum, store_cols, currentstock)`.

---

## Customers (separate from product CATEGORY)

- Table: `CUSTOMER`
- `CUSTOMER.CUSTOMERCATEGORY` → `TBLCUSTOMERCATEGORY` (customer segment, **not** product category)

---

## What MamaHub should reuse

| Priority | Nexus file | Use in MamaHub |
|----------|------------|----------------|
| 1 | `db/itemmaster_detail_select.py` | Item detail JOINs |
| 2 | `db/__init__.py` → `get_items_list`, `get_categories` | Product APIs |
| 3 | `addons/itemmaster/controllers/routes.py` | API contract for listing |
| 4 | `addons/core/schema/generated/oracle_schema_rfim.py` | Column name reference |

---

## MamaHub mapping decision

| E-commerce concept | Use in MamaHub |
|--------------------|----------------|
| Product | `ITEMMASTER` |
| Category tree | `CATEGORY` (M → D → C) |
| Brand | `CATEGORY` (`FLAG='B'`) + optional `MH_BRAND` for marketing slugs |
| Age groups / interests | `MH_AGE_GROUP`, `MH_INTEREST` (e-commerce only) |
| Stock | `WAREHOUSE_STOCK` + `CURRENTSTOCK` |
| Images | `PRODUCT_IMAGES` (to be wired) |

Do **not** create a new `PRODUCT` or `BRAND` ERP table — use existing Nexus patterns.
