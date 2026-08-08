"""
Application settings. Database credentials are loaded from environment variables
or from a .env file (see .env.example).
"""
import os
DB_USERNAME = os.getenv('DB_USERNAME', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_DSN = os.getenv('DB_DSN', '')
AUTH_DB_USERNAME = os.getenv('AUTH_DB_USERNAME', '')
AUTH_DB_PASSWORD = os.getenv('AUTH_DB_PASSWORD', '')
AUTH_DB_DSN = os.getenv('AUTH_DB_DSN', '')
CENTRAL_REPORT_USER = os.getenv('CENTRAL_REPORT_USER', '')
CENTRAL_REPORT_PASSWORD = os.getenv('CENTRAL_REPORT_PASSWORD', '')
CENTRAL_REPORT_DSN = os.getenv('CENTRAL_REPORT_DSN', '')
CENTRAL_REPORT_LINKS = os.getenv('CENTRAL_REPORT_LINKS', 'EMDADCO=emdadco_link,RFSS=rfss_link,RFIL=rfil_link')
RFIM_USERNAME = os.getenv('RFIM_USERNAME', '')
RFIM_PASSWORD = os.getenv('RFIM_PASSWORD', '')
RFIM_DSN = os.getenv('RFIM_DSN', '')

def get_db_config():
    """Return dict with user, password, dsn for the single/default database."""
    return {'user': (os.getenv('DB_USERNAME') or '').strip(), 'password': os.getenv('DB_PASSWORD') or '', 'dsn': (os.getenv('DB_DSN') or '').strip()}

def get_auth_db_config():
    """Return dict with user, password, dsn for the auth (login) database."""
    return {'user': (os.getenv('AUTH_DB_USERNAME') or '').strip(), 'password': os.getenv('AUTH_DB_PASSWORD') or '', 'dsn': (os.getenv('AUTH_DB_DSN') or '').strip()}

def is_multi_db_mode():
    """True when auth DB is configured; then login uses auth DB and business data uses tenant DB per user.

    Override with ``MULTI_DB_MODE`` after editing ``.env`` and restarting the Flask process:

    - ``0``, ``false``, ``no``, ``off``, ``single`` → force single-DB (uses ``DB_USERNAME`` / ``DB_DSN`` only).
    - ``1``, ``true``, ``yes``, ``on``, ``multi`` → force multi-DB if ``AUTH_DB_*`` is complete.
    When unset, multi-DB is on iff both ``AUTH_DB_USERNAME`` and ``AUTH_DB_DSN`` are non-empty.
    """
    raw = (os.getenv('MULTI_DB_MODE') or '').strip().lower()
    if raw in ('0', 'false', 'no', 'off', 'single'):
        return False
    if raw in ('1', 'true', 'yes', 'on', 'multi'):
        cfg = get_auth_db_config()
        return bool(cfg.get('dsn') and cfg.get('user'))
    cfg = get_auth_db_config()
    return bool(cfg.get('dsn') and cfg.get('user'))

def get_central_report_config():
    """Config for Stock Report Central when using DB links: user, password, dsn, and tenant->link mapping."""
    auth = get_auth_db_config()
    user = (CENTRAL_REPORT_USER or '').strip() or (auth.get('user') or '')
    password = CENTRAL_REPORT_PASSWORD if (CENTRAL_REPORT_USER or '').strip() else auth.get('password') or ''
    dsn = (CENTRAL_REPORT_DSN or '').strip() or (auth.get('dsn') or '')
    links_str = (CENTRAL_REPORT_LINKS or '').strip()
    links = {}
    for part in links_str.split(','):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            links[(k or '').strip().upper()] = (v or '').strip()
    return {'user': user, 'password': password, 'dsn': dsn, 'links': links}

def use_central_links_for_report():
    """True when central report user and DSN are configured and at least one link is set."""
    cfg = get_central_report_config()
    return bool(cfg.get('dsn') and cfg.get('user') and cfg.get('links'))

def get_rfim_schema_config():
    """Credentials for introspecting RFIM schema (does not replace auth/tenant routing in Flask)."""
    return {'user': RFIM_USERNAME, 'password': RFIM_PASSWORD, 'dsn': RFIM_DSN}
