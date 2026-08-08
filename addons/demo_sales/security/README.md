# Security (demo_sales)

In Odoo you would use `ir.model.access.csv` and record rules. In this app:

- **Role → menu** mapping lives in `permissions.py` (`MENU_GROUPS` and `menu_path` values).
- Assign **Demo Sales** menu items to roles via the existing Roles UI, or grant `allow_all` for admins.
- **`menu_definitions.py`** — Python mirror of `menu_path` → label (pair with `permissions.py`).

Optional future files here:

- `record_rules.md` — human-readable row-level rules (e.g. “sales user sees only own team”).
- `menu.xml` — if you later generate `base.html` from XML/JSON (not required today).
