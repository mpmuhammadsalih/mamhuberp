# GL accounting dimensions (cost center, department, project)

This document describes **analytic dimensions** on general-ledger voucher lines: what was added, how to configure mandatory rules, how to post from Python, and how to report.

## What was implemented

### 1. Columns on `GL_VOUCHER_DTL`

Each voucher line can carry up to three optional codes (VARCHAR2(30), nullable):

| Column         | Meaning (typical use)   |
|----------------|-------------------------|
| `COST_CENTER`  | Cost / profit center    |
| `DEPARTMENT`   | Department / division   |
| `PROJECT`      | Project / job / phase   |

Existing databases get these columns automatically the next time `ensure_gl_tables()` runs (for example on first GL post or journal list). New installs create the table with the columns already present.

### 1b. Dimension value master (`GL_DIMENSION_VALUE`)

Optional **catalog** of allowed codes per dimension type (`COST_CENTER`, `DEPARTMENT`, `PROJECT`): code, display name, active flag, sort order.

- **Where to maintain it in the UI:** **Setup** (sidebar) → **GL dimension master** — URL `/setup/gl-dimensions`.
- **Permission:** menu path `setup.gl_dimension_master` (grant via **Roles & Permissions**), or use users **admin** / **super** who always have access.
- **Python:** `list_gl_dimension_values`, `upsert_gl_dimension_value`, `delete_gl_dimension_value`, `get_gl_dimension_value_row`, `ensure_gl_dimension_value_table` in `db`.

Posting does **not** yet enforce “code must exist in master” unless you add that check later; the master is mainly for consistent codes and future validation / dropdowns.

### 2. Rules table `GL_ACCOUNT_DIMENSION_RULE`

Optional **per account** requirements (Oracle table, tenant DB):

| Column                 | Values | Meaning                          |
|------------------------|--------|----------------------------------|
| `ACCOUNT_CODE`         | PK     | Chart of Accounts code (trimmed, stored uppercase in API) |
| `REQUIRE_COST_CENTER`  | Y / N  | If Y, line must have cost center after defaults merge |
| `REQUIRE_DEPARTMENT`   | Y / N  | If Y, line must have department |
| `REQUIRE_PROJECT`      | Y / N  | If Y, line must have project    |

If there is **no row** for an account, **no** dimension is required for that account.

The table is created when you first use the helpers below (or on posting via `create_gl_journal_entry`).

### 3. Python API (`db` module)

| Function | Purpose |
|----------|---------|
| `list_gl_dimension_values(dim_type=None, include_inactive=False)` | Master rows from `GL_DIMENSION_VALUE`. |
| `upsert_gl_dimension_value(dim_type, dim_code, dim_name, active, sort_order)` | Insert/update one master row. |
| `delete_gl_dimension_value(dim_type, dim_code)` | Remove one master row. |
| `resolve_gl_line_dimensions(line, dimension_defaults)` | Merge line dict + header/session defaults (see precedence). |
| `get_gl_dimension_requirements_for_account(account_code)` | Returns `require_cost_center` / `require_department` / `require_project` booleans. |
| `list_gl_account_dimension_rules()` | List all configured rules. |
| `upsert_gl_account_dimension_rule(account_code, require_cost_center, require_department, require_project)` | Set Y/N for one account. Returns `(ok, err_msg)`. |
| `create_gl_journal_entry(..., dimension_defaults=None)` | Same as before, plus optional dimensions (see below). |
| `get_gl_voucher_detail(voucher_no)` | Line dicts include `cost_center`, `department`, `project` when columns exist. |
| `get_account_ledger(...)` | Each line may include the same keys. |
| `get_gl_ledger_map_for_account_codes(...)` | Each detail line may include the same keys. |
| `get_trial_balance_by_dimension(dimension, date_from, date_to)` | TB grouped by **account + one** dimension; `dimension` is `cost_center`, `department`, or `project`. |

**Tenant DB:** all of the above use `_get_connection()` (business / tenant data), not the auth DB.

---

## How to use it

### A. Create dimension codes (Setup UI)

1. Open **Setup → GL dimension master**.
2. Choose **Dimension type**, enter **Code** (stored uppercase) and optional **Name**, **Sort order**, and **Active**.
3. Use **Edit** / **Delete** from the list. Filter by type or include inactive rows from the filter bar.

### B. Configure which accounts require dimensions

From Python (admin script, shell, or future UI):

```python
from db import upsert_gl_account_dimension_rule

ok, err = upsert_gl_account_dimension_rule(
    "5100",                      # expense account example
    require_cost_center="Y",
    require_department="N",
    require_project="Y",
)
if not ok:
    print(err)
```

List rules:

```python
from db import list_gl_account_dimension_rules
print(list_gl_account_dimension_rules())
```

### C. Post a journal with dimensions

**Journal Entry screen (Accounts):** **Accounts → Journal Entry** includes optional **default** cost center / department / project (applied when a line leaves those fields blank) and **per-line** columns **Cost ctr**, **Dept**, **Project**. Posted vouchers show these on the voucher detail page.

**Per line (API):** set any of `cost_center`, `department`, `project` (aliases: `COST_CENTER`, `DEPT`, `PROJECT`, etc. — see `resolve_gl_line_dimensions`).

**Header / session defaults:** pass `dimension_defaults` so every line inherits unless overridden.

```python
from db import create_gl_journal_entry

voucher_no = create_gl_journal_entry(
    voucher_date="2026-05-11",
    reference_no="JV-MANUAL-01",
    narration="Month-end accrual",
    lines=[
        {
            "account_code": "5100",
            "debit": 1000.00,
            "credit": 0,
            "remarks": "Expense",
            "project": "PRJ-2026-01",   # line-level override example
        },
        {
            "account_code": "2000",
            "debit": 0,
            "credit": 1000.00,
            "remarks": "Accrued liability",
        },
    ],
    created_by="admin",
    source="MANUAL",
    dimension_defaults={
        "cost_center": "CC-HO",
        "department": "FIN",
        # "project": None  # optional
    },
)
```

**Precedence (merge order):**

1. Explicit value on the **line** (first matching key among aliases).  
2. Else value from **`dimension_defaults`** for that dimension.  
3. Else blank (allowed unless the account’s rule requires that dimension).

**Validation:** after merge, if `GL_ACCOUNT_DIMENSION_RULE` requires a dimension for that `account_code` and the value is still blank, `create_gl_journal_entry` raises `ValueError` with a clear message.

### D. Subledgers (GRN, AP payment, etc.)

Paths that **insert `GL_VOUCHER_DTL` directly** (for example GRN posting in `purchase` routes) **do not** automatically populate these columns yet. They remain `NULL` until you extend those `INSERT` statements to pass the same fields (or call `create_gl_journal_entry` with a built `lines` list).

**Recommendation until migrated:**

- Do not set **strict** rules on accounts used only by raw SQL postings, **or**
- Add `dimension_defaults` / line fields when you refactor those postings to one shared GL builder.

### E. Reporting

**Classic trial balance (by account only):** unchanged — `get_trial_balance_report`.

**By one analytic dimension** (account × bucket, e.g. cost center):

```python
from db import get_trial_balance_by_dimension

rows = get_trial_balance_by_dimension(
    "cost_center",
    date_from="2026-01-01",
    date_to="2026-05-31",
)
# each row: code, name, type, dimension, dim_value, debit, credit, balance
```

Blank dimension values on lines appear as `dim_value == "(blank)"` so you can spot missing analytics.

**Account ledger:** `get_account_ledger` line dicts include `cost_center`, `department`, `project` when the columns exist.

---

## Design notes (why this shape)

- **Fixed columns** on `GL_VOUCHER_DTL` keep queries and trial balance simple; three dimensions cover many SMEs without a full “dimension set” engine.
- **Rules in a separate table** avoid altering `CHART_OF_ACCOUNTS` and keep requirements optional per install.
- **Defaults on `create_gl_journal_entry`** give one place to inject branch / document header context without repeating on every line.

---

## Optional next steps

1. Admin UI for `GL_ACCOUNT_DIMENSION_RULE` (list + edit).  
2. Manual journal HTML form: three fields per line + “apply defaults to all lines”.  
3. Refactor GRN / AP / other postings to set dimensions (or call a single `build_gl_lines(...)` helper).  
4. Value validation: optional `GL_DIMENSION_VALUE` master (type + code + active flag) and validate codes before insert.

For questions or changes to column names / count, extend `ensure_gl_tables` and the same Python helpers in lockstep.
