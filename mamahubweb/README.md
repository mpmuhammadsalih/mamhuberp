# MamaHub — storefront + SQL

Production-oriented children’s toy e-commerce **React storefront**, backed by **Nova ERP** for API and admin.

| Layer | Location |
|-------|----------|
| Storefront UI | `frontend/` → http://localhost:5173 |
| Customer API (`/api/v1/*`) | Nova `storefront_backend` |
| Ecommerce admin | Nova → **Ecommerce** menu |
| Oracle `MH_*` scripts | `sql/` in this repo |

## Quick start

### 1. Nova ERP (API + admin)

```powershell
cd d:\webapps\Nova
python app.py
```

Default port is set in Nova `.env` (`FLASK_PORT`, e.g. **5055**).

### 2. MamaHub frontend

```powershell
cd d:\webapps\MAMAHUBWEB\frontend
npm install
npm run dev
```

Create `frontend/.env.local` if Nova is not on the Vite default:

```env
VITE_API_PROXY=http://127.0.0.1:5055
```

Open http://localhost:5173 — `/api` proxies to Nova.

### 3. Apply Oracle schema (optional)

```powershell
cd d:\webapps\MAMAHUBWEB
pip install -r scripts/requirements.txt
# Set ORACLE_* in repo-root .env (copy from .env.example)
python scripts/apply_schema.py
```

Policy: create-if-missing only — see `sql/SCHEMA_POLICY.md`.

## Repository layout

```text
MAMAHUBWEB/
├── frontend/          React storefront (Vite)
├── sql/               Oracle MH_* DDL/DML
├── scripts/           apply_schema.py, utilities
├── docs/              ERP integration notes
└── deploy/            Legacy nginx config (optional)
```

## Database

Details: `sql/SCHEMA_POLICY.md`  
Nexus ERP patterns: `docs/NEXUS_ERP_REFERENCE.md`

Set branch scope in Nova: `DEFAULT_LOCATION_CODE=1`.

## License

Proprietary — MamaHub / mamahub.store
