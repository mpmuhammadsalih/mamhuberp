# Mobile backend

JWT REST API for the Nexa Mobile Flutter app (`D:\webapps\Nexa_Mobile_FastAPI\flutter_app`).

Runs **inside** Nexa Dynamics — same process as the web ERP (`python app.py`).

## Layout

| Path | Purpose |
|------|---------|
| `routes/` | `/api/v1/*` FastAPI routers |
| `services/` | Business logic (stock count, GRN, auth, …) |
| `database/` | Oracle bridge to Dynamics `db.py` |
| `sql/` | Optional tenant DDL scripts |
| `bootstrap.py` | CORS, middleware, error handlers (called from `app.py`) |
| `deps_auth.py` | JWT + RBAC |
| `config.py` | Reads main project `.env` |

## Endpoints

- `POST /api/v1/auth/login`
- `GET /api/v1/stock-count/sessions`
- `GET /health`
- …see `routes/`

## Registration

Addon stub: `addons/mobile_api/__manifest__.py` → `mobile_backend:bp`

## Flutter

Point the app at Dynamics (port from `FLASK_PORT`, default **5051**):

```powershell
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:5051
```

## Env (in project root `.env`)

```env
JWT_SECRET_KEY=...
JWT_ACCESS_MINUTES=20
JWT_REFRESH_DAYS=30
CORS_ORIGINS=*
```

## Mutations (required for new write endpoints)

All insert/update/delete operations must use:

1. **`oracle_transaction(conn)`** in services — see `database/transaction.py`
2. **`require_save_nonce`** + **`success_after_mutation`** on routes — see `deps_save.py`

Full guide: **[MUTATIONS.md](./MUTATIONS.md)**
