# Receivables Module (Flask + Oracle)

This app connects to your Oracle database and reads from:
- `tblsettlent`
- `tbltempsettlement`
- `customers` view (joined on `customercode`)

It also creates a `login_users` table for authentication.

## Setup

1. Create a virtual env and install deps:
   ```
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Set environment variables (PowerShell example):
   ```
   $env:FLASK_SECRET_KEY="change-me"
   $env:ORACLE_HOST="192.168.1.225"
   $env:ORACLE_PORT="1521"
   $env:ORACLE_SERVICE="rgc"
   $env:ORACLE_USER="rfim"
   $env:ORACLE_PASSWORD="rfim"
   ```

3. Create a login user:
   ```
   python scripts/create_user.py
   ```

4. Run the app:
   ```
   python app.py
   ```

Open `http://127.0.0.1:5002` in your browser (override with env `FLASK_PORT` or `PORT`).

## Notes

- `login_users` is created automatically on first run if it does not exist.
- Default login is `admin` / `admin123` (created if missing).
- Update table/view names in `db.py` if your schema uses different names.
- Uses **python-oracledb** (thin mode by default — no Instant Client required). For **Oracle Autonomous DB without a wallet**, paste the TLS connection string from OCI into `DB_DSN`, or set `ORACLE_USE_TCPS=1` with `host:1522/service_name`. See `.env.example`.
- Dashboard grouping column can be overridden with:
  `DASH_SALESMAN_COLUMN`, `DASH_CUSTOMER_NAME_COLUMN`,
  `DASH_SALESMAN_NAME_COLUMN`.
