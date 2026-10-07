# Odoo-style addons (modules)

This project organizes HTTP features like **Odoo addons**: each installable folder under **`addons/<technical_name>/`** holds **`controllers/routes.py`**, **`views/templates/`**, optional **`models/`**, **`static/`**, **`__manifest__.py`**, and an **`addons.<name>:bp`** registration hook.

Routes are discovered from **`addons/*/ __manifest__.py`** and loaded in **`app.py`** via **`register_addon_blueprints(app)`** only (`blueprints/` is retired).

---

## Odoo `sale/` layout ↔ this project

Odoo’s module tree is a good **mental model**. We keep the same separation of concerns; **file formats differ** where Odoo uses XML/CSV and this stack uses Python + Jinja.

| Odoo (example) | Here | Notes |
|----------------|------|--------|
| `__manifest__.py` | **`__manifest__.py`** (`MANIFEST`) | Same idea: name, version, deps, `installable`, Flask `blueprint_ref`. |
| `models/` | **`models/`** | DTOs / repositories calling shared `db` helpers (no Odoo ORM). |
| `views/*.xml` | **`views/templates/**/*.html`** | UI is **Jinja**, not XML records; group under `views/templates/<addon>/`. |
| `controllers/main.py` | **`controllers/routes.py`** | Flask Blueprint + routes; **`__init__.py`** may export **`bp`**. |
| `static/` | **`static/`** | CSS/JS/images; served via Blueprint `static_folder` (same idea as Odoo). |
| `security/*.xml`, `ir.model.access.csv` | **`permissions.py`** (+ DB roles) + optional **`security/`** | Central RBAC (`menu_path`, endpoints); addon **`security/`** mirrors labels for docs/tooling. Not CSV/XML. |
| `data/*.xml` | **`data/`** *(optional)* | Seeds: SQL scripts, JSON fixtures, or calls from `db`/migrations—no `noupdate` XML. |
| `wizard/` | **`wizard/`** *(optional)* | Multi-step or popup flows: extra routes + templates/partials; same pattern, no Odoo `TransientModel`. |
| `report/` | **`report/`** *(optional)* | Printable/PDF templates or report-specific code; or live under `views/templates` if small. |
| *(services)* | **`services/`** *(recommended)* | Orchestration between controllers and `models/` (optional in Odoo Python modules, common here). |

So: **yes—we keep the same capsule** (`models`, `views`, `controllers`, `static`, `security` concept, optional `data` / `wizard` / `report`). Only **`views` are HTML/Jinja** instead of XML, and **access control** is expressed in **`permissions.py`** and your auth DB, not `ir.model.access.csv`.

---

## Folder layout

```
addons/
├── README.md                    # This file
├── register.py                  # Flask: register_addon_blueprints(app)
├── core/
│   ├── manifest_loader.py       # Discover addons + load __manifest__.py
│   └── menu_registry.py         # Addon meta aggregation for tooling
├── demo_sales/                  # Example module — one folder = package + blueprint + models + templates + static
│   ├── __init__.py              # Re-exports ``bp`` → ``blueprint_ref``: ``addons.demo_sales:bp``
│   ├── __manifest__.py          # MANIFEST dict (Odoo convention)
│   ├── controllers/
│   │   └── routes.py            # Flask Blueprint: set template_folder + static_folder here
│   ├── models/
│   │   └── sale_order.py        # DTOs / thin adapters into db.py
│   ├── views/
│   │   ├── README.md
│   │   └── templates/demo_sales/*.html
│   ├── static/                  # Module CSS/JS/images (like Odoo addon static/)
│   │   ├── README.md
│   │   └── css/demo_sales.css  # Served as /demo-sales/static/css/... via Blueprint
│   ├── services/
│   │   └── dashboard.py         # Business rules / orchestration
│   └── security/
│       ├── README.md
│       └── menu_definitions.py    # Mirror menu_path labels (doc + tooling)
```


## Bundled static (CSS / JS per addon)

Like **Odoo’s `static/` inside each module**, keep module-specific assets next to the Blueprint:

1. **`controllers/routes.py`** — `Blueprint(..., static_folder=str(_ADDON_ROOT / "static"), ...)`.
2. **`static/css/<module>.css`** (optional **`static/js/`**).
3. **Templates** — `{% block extra_css %}` with `url_for('<blueprint_name>.static', filename='css/....')`.

Global app assets stay under the project **`static/`** at the Flask app root; addon assets are namespaced by URL (`/demo-sales/static/...`) and avoid cluttering global CSS.

---

## Blueprint + models in the same module

Each installable addon is **one Python package** under `addons/<technical_name>/`:

- **`models/`** — DTOs, repositories (calls into shared **`db`**). Every addon ships at least **`models/__init__.py`** and a **`<technical_name>_models.py`** scaffold; **`flask.models_package`** in **`__manifest__.py`** points to **`addons.<name>.models`** (see **`menu_registry`**).
- **`controllers/routes.py`** — defines the Flask **`Blueprint`** (HTTP only).
- **`__init__.py`** — re-exports **`bp`** so registration uses **`addons.<tech>:bp`** (same package as **`models`**).

Optional manifest key **`flask.models_package`** documents the models entry point for tooling (`addons/core/menu_registry.py` includes it in summaries).

---

## Layers (clean architecture)

| Layer | Responsibility | Depends on |
|-------|----------------|------------|
| **controllers/** | HTTP: Blueprint, request/response, status codes | services, Flask session |
| **services/** | Rules, orchestration | models, `db` helpers |
| **models/** | DTOs, queries delegated to `db.py` | `db` |
| **views/** | Jinja only | context from controllers |
| **security/** | Document `menu_path` ids; aligns with **permissions.py** | — |

**Rule:** controllers → services → models. Never skip services for non-trivial rules.

---

## Manifest (`__manifest__.py`)

Each addon exports **`MANIFEST`**. Flask wiring:

- **`flask.blueprint_ref`** — prefer **`addons.<technical_name>:bp`** so the Blueprint is colocated with **`addons.<name>.models`** in one package.
- **`flask.models_package`** (optional) — e.g. **`addons.demo_sales.models`** for tooling / docs.

- **`installable`: False** — skipped by `register_addon_blueprints`.
- **`urls.prefix`** — documentation / OpenAPI symmetry (not enforced by Flask).

---

## Menu system ↔ RBAC

1. **`permissions.py`** — `MENU_GROUPS` with **`menu_path`**, **`endpoints`**, **`blueprints`**. Roles UI assigns paths.

2. **`templates/base.html`** — `has_menu_permission('demo_sales.dashboard')` and `url_for('demo_sales.orders')`.

3. Optional: **`addons/<name>/security/menu_definitions.py`** — same ids as **`menu_path`**, human labels.

Adding a submenu: new route endpoint → append to **`endpoints`** → add **`views/...html`** → link from sidebar.

---

## Registering addons

In **`app.py`** → **`create_app()`**:

```python
from addons.register import register_addon_blueprints
register_addon_blueprints(app)
```

That is the **only** blueprint registration (`installable` addons with valid **`flask.blueprint_ref`**). Shared shells stay in **`templates/base.html`**, **`unauthorized.html`**, etc.

---

## Independence

- Tenant routing stays **`db.py`** / `g`; addon routes call existing helpers.
- **`permissions.py`** + **`templates/base.html`** drive menu visibility for new endpoints.
- See **`addons/demo_sales/`** for a layered reference (`models/`, `services/`, `static/`).

---

## Former `blueprints/` package

Former **`blueprints/*.py`** files (auth, dashboard, api, reports, HO, tenants, POS, SMS, notifications, promotions, salesman summary, supplier, customer, roles, employee, users, employees, …) live under **`addons/<technical_name>/`**. **`blueprints/__init__.py`** remains empty for compatibility tooling.

Accounts Online (`temporary_*`) and Accounts (`accounts`) are described in manifests under **`category`** where applicable.

---
