"""Utilities — single-DB vs multi-DB configuration guide."""
from pathlib import Path
from nexa_http import Blueprint, abort, render_template, session
from config.settings import get_auth_db_config, get_db_config, is_multi_db_mode
_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint('utilities_db_modes', __name__, url_prefix='/utilities', template_folder=str(_ADDON / 'views' / 'templates'))

def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import get_role_permissions
        from db import get_user_role_id
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'utilities.database_modes_guide' in perms
    except Exception:
        return False

@bp.route('/database-modes-guide', methods=('GET',))
def database_modes_guide_page():
    """Static help page: .env and tenant_databases for single vs multi-DB."""
    if not session.get('user'):
        abort(401)
    if not _allowed():
        abort(403)
    auth = get_auth_db_config()
    main = get_db_config()
    return render_template('database_modes_guide.html', is_multi_db_mode=is_multi_db_mode(), auth_user_set=bool((auth.get('user') or '').strip()), auth_dsn_set=bool((auth.get('dsn') or '').strip()), main_user_set=bool((main.get('user') or '').strip()), main_dsn_set=bool((main.get('dsn') or '').strip()))
