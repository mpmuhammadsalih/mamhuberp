"""Layout data cache for menu/permissions (in-process; not stored in session cookie)."""

from __future__ import annotations



from typing import Any, Dict, Optional



_LAYOUT_KEY = '_nexa_layout_v1'

# Menu permission lists can exceed browser cookie limits (~4KB). Keep payload in memory.

_layout_mem_cache: Dict[str, Dict[str, Any]] = {}





def _cache_key(username: str) -> str:

    return (username or '').strip().upper()





def invalidate_layout_cache(session: Any) -> None:

    try:

        user = (session.get('user') or session.get(_LAYOUT_KEY, {}).get('user') or '').strip()

        if user:

            _layout_mem_cache.pop(_cache_key(user), None)

        session.pop(_LAYOUT_KEY, None)

    except Exception:

        pass





def warm_layout_cache(session: Any, username: str) -> None:

    """Load menu/permission flags once (e.g. at login) instead of every page request."""

    from db import (

        get_employee_outstanding_count,

        get_role_permissions,

        get_role_quick_access,

        get_user_by_username,

        get_user_role_id,

    )



    user = (username or '').strip()

    if not user:

        invalidate_layout_cache(session)

        return



    role_id = get_user_role_id(user)

    menu_permissions: list[str] = []

    quick_access_paths: list[str] = []

    allow_all = role_id is None

    if role_id:

        menu_permissions = get_role_permissions(role_id)

        quick_access_paths = get_role_quick_access(role_id)



    row = get_user_by_username(user) or {}

    user_transit_only = str(row.get('transit_only') or 'N').strip().upper() == 'Y'

    user_customer_creation = str(row.get('customer_creation') or 'N').strip().upper() == 'Y'



    cr_alert_poll_enabled = True

    tx_recording_enabled = True

    try:

        from addons.ho.customer_alert_control import (

            get_customer_request_alert_poll_enabled,

            get_transaction_recording_enabled,

        )

        if user_customer_creation or allow_all:

            cr_alert_poll_enabled = get_customer_request_alert_poll_enabled('HO')

        tx_recording_enabled = get_transaction_recording_enabled('HO')

    except Exception:

        pass



    outstanding_due_count = 0

    employeecode = session.get('employeecode')

    if employeecode:

        try:

            from permissions import is_menu_path_allowed

            if allow_all or is_menu_path_allowed('notifications.outstanding_due', menu_permissions):

                outstanding_due_count = get_employee_outstanding_count(employeecode)

        except Exception:

            pass



    payload = {

        'user': user,

        'role_id': role_id,

        'menu_permissions': menu_permissions,

        'quick_access_paths': quick_access_paths,

        'allow_all_permissions': allow_all,

        'user_transit_only': user_transit_only,

        'user_customer_creation': user_customer_creation,

        'cr_alert_poll_enabled': cr_alert_poll_enabled,

        'tx_recording_enabled': tx_recording_enabled,

        'outstanding_due_count': outstanding_due_count,

    }

    _layout_mem_cache[_cache_key(user)] = payload

    # Session cookie: small marker only (full payload stays in worker memory).

    session[_LAYOUT_KEY] = {'user': user, 'role_id': role_id}





def peek_layout_cache(username: str) -> Optional[Dict[str, Any]]:
    """Return in-memory layout cache only (no DB warm on miss). Used by security middleware."""
    user = (username or '').strip()
    if not user:
        return None
    mem = _layout_mem_cache.get(_cache_key(user))
    if isinstance(mem, dict) and (mem.get('user') or '').strip() == user:
        return mem
    return None


def get_layout_cache(session: Any, username: str) -> Optional[Dict[str, Any]]:

    user = (username or '').strip()

    if not user:

        return None

    mem = _layout_mem_cache.get(_cache_key(user))

    if isinstance(mem, dict) and (mem.get('user') or '').strip() == user:

        return mem

    warm_layout_cache(session, user)

    mem = _layout_mem_cache.get(_cache_key(user))

    return mem if isinstance(mem, dict) else None

