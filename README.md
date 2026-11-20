# Nexa Mobile (Flutter)

The **mobile API backend** was merged into **Nexa Dynamics FastAPI**:

- API: `D:\webapps\Nexa_Dynamics_FastAPI\addons\mobile_api\` → `/api/v1/*`
- Canonical Flutter copy: `D:\webapps\Nexa_Dynamics_FastAPI\mobile_client\`

This folder keeps the Flutter app only. Run the ERP server from Dynamics first, then run Flutter here or from `mobile_client`.

## 1. Start backend (Dynamics — one server for web + mobile)

```powershell
cd D:\webapps\Nexa_Dynamics_FastAPI
python app.py
```

Default URL: `http://127.0.0.1:5051` (see `FLASK_PORT` in Dynamics `.env`).

Add to Dynamics `.env` if needed:

```env
JWT_SECRET_KEY=your-secret
JWT_ACCESS_MINUTES=20
JWT_REFRESH_DAYS=30
CORS_ORIGINS=*
```

## 2. Run Flutter (this folder)

```powershell
cd flutter_app
flutter pub get
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:5051
```

| Device | API URL |
|--------|---------|
| Windows / iOS simulator | `http://127.0.0.1:5051` |
| Android emulator | `http://10.0.2.2:5051` |
| Physical phone | `http://YOUR_PC_LAN_IP:5051` |

Or set the URL in the app **App Configuration** screen.

## Removed (no longer in this repo)

- `erp_api/` — use Dynamics `addons/mobile_api/`
- `scripts/` — optional DB tools; run from Dynamics if needed
