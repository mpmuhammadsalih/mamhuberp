"""Per-user default warehouses by document type (auth DB ``login_users``)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

USER_WH_KINDS = ('sales', 'sales_return', 'purchase', 'purchase_return')

_WH_COL_BY_KIND: Dict[str, str] = {
    'sales': 'DEFAULT_WH_SALES',
    'sales_return': 'DEFAULT_WH_SALES_RETURN',
    'purchase': 'DEFAULT_WH_PURCHASE',
    'purchase_return': 'DEFAULT_WH_PURCHASE_RETURN',
}

_FORM_FIELD_BY_KIND: Dict[str, str] = {
    'sales': 'default_wh_sales',
    'sales_return': 'default_wh_sales_return',
    'purchase': 'default_wh_purchase',
    'purchase_return': 'default_wh_purchase_return',
}


def ensure_login_user_default_warehouse_columns(cur: Any, cols: set) -> None:
    """Add nullable NUMBER columns on ``login_users`` when missing."""
    upper = {str(c).upper() for c in (cols or [])}
    for col in _WH_COL_BY_KIND.values():
        if col not in upper:
            cur.execute(f'ALTER TABLE login_users ADD {col} NUMBER')
            upper.add(col)


def parse_optional_warehouse_id(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        wid = int(float(text))
    except (TypeError, ValueError):
        return None
    return wid if wid > 0 else None


def warehouse_prefs_from_mapping(data: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Extract warehouse IDs from form dict / user row."""
    src = data or {}
    out: Dict[str, Optional[int]] = {}
    for kind, field in _FORM_FIELD_BY_KIND.items():
        out[kind] = parse_optional_warehouse_id(src.get(field))
        if out[kind] is None:
            col = _WH_COL_BY_KIND[kind].lower()
            out[kind] = parse_optional_warehouse_id(src.get(col))
    return out


def warehouse_prefs_sql_columns() -> str:
    return ', '.join(f'u.{c} AS {c.lower()}' for c in _WH_COL_BY_KIND.values())


def warehouse_prefs_insert_columns() -> Tuple[str, str]:
    cols = list(_WH_COL_BY_KIND.values())
    return ', '.join(cols), ', '.join(f':{c.lower()}' for c in cols)


def warehouse_prefs_insert_params(prefs: Dict[str, Optional[int]]) -> Dict[str, Any]:
    return {col.lower(): prefs.get(kind) for kind, col in _WH_COL_BY_KIND.items()}


def warehouse_prefs_update_clauses() -> List[str]:
    return [f'{col} = :{col.lower()}' for col in _WH_COL_BY_KIND.values()]


def get_user_default_warehouse_id(username: Optional[str], doc_kind: str) -> Optional[int]:
    """Return configured warehouse id for user + document kind, or None (no restriction)."""
    kind = (doc_kind or '').strip().lower()
    if kind not in _WH_COL_BY_KIND:
        return None
    uname = (username or '').strip()
    if not uname:
        return None
    from db import _safe_rows_auth, ensure_login_table

    ensure_login_table()
    col = _WH_COL_BY_KIND[kind]
    rows = _safe_rows_auth(
        f'SELECT {col} AS wh_id FROM login_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))',
        {'u': uname},
    )
    if not rows:
        return None
    return parse_optional_warehouse_id(rows[0].get('wh_id'))


def filter_warehouse_picker_rows(
    rows: Optional[List[Dict[str, Any]]],
    warehouse_id: Optional[int],
) -> List[Dict[str, Any]]:
    """When ``warehouse_id`` is set, keep only that warehouse in picker rows."""
    base = list(rows or [])
    wid = parse_optional_warehouse_id(warehouse_id)
    if not wid:
        return base
    key = str(wid)
    filtered = [r for r in base if str(r.get('code') or r.get('warehouse_id') or '').strip() == key]
    if filtered:
        return filtered
    # Configured warehouse missing from active list — still expose it for display/validation.
    return [{'code': key, 'warehouse_code': key, 'name': key}]


def warehouse_has_positive_stock(warehouse_id: int, location_code: Optional[int] = None) -> bool:
    """True when WAREHOUSE_STOCK has qty > 0 for this warehouse (current tenant DB)."""
    try:
        wid = int(warehouse_id)
    except (TypeError, ValueError):
        return False
    if wid <= 0:
        return False
    try:
        from db import WAREHOUSE_STOCK_TABLE, _safe_rows, _table_exists, ensure_warehouse_stock_table

        if not ensure_warehouse_stock_table() or not _table_exists(WAREHOUSE_STOCK_TABLE):
            return True  # no stock table — do not treat as empty
        params: Dict[str, Any] = {'wid': wid}
        loc_sql = ''
        if location_code is not None:
            try:
                params['loc'] = int(location_code)
                loc_sql = ' AND LOCATIONCODE = :loc'
            except (TypeError, ValueError):
                pass
        probe = _safe_rows(
            f'SELECT 1 FROM {WAREHOUSE_STOCK_TABLE} '
            f'WHERE WAREHOUSE_ID = :wid{loc_sql} AND NVL(QTY, 0) > 0 AND ROWNUM = 1',
            params,
        )
        return bool(probe)
    except Exception:
        return True


def apply_user_warehouse_filter(
    username: Optional[str],
    doc_kind: str,
    rows: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Restrict picker to the user's default warehouse when configured.

    If that warehouse has no positive stock, keep the full list so Sales/Purchase
    item pickers are not trapped on an empty store (e.g. WH001 with only zero qty).
    """
    base = list(rows or [])
    wid = get_user_default_warehouse_id(username, doc_kind)
    if not wid:
        return base
    filtered = filter_warehouse_picker_rows(base, wid)
    if len(base) <= 1:
        return filtered
    try:
        from nexa_http.session_wrap import session

        loc = session.get('location_code')
    except Exception:
        loc = None
    if warehouse_has_positive_stock(wid, loc):
        return filtered
    return base


def build_warehouse_picker_rows(location_code: int, search: str = '', limit: int = 300) -> List[Dict[str, str]]:
    """Active warehouses for pickers — ``code`` is ``WAREHOUSE_ID`` (session/tenant DB)."""
    q = (search or '').strip().lower()
    lim = max(1, min(int(limit or 300), 500))
    try:
        loc = int(location_code)
    except (TypeError, ValueError):
        loc = 1

    def _matches(wh_code: str, wh_name: str, wid: int) -> bool:
        if not q:
            return True
        return q in f'{wh_code} {wh_name} {wid}'.lower()

    from db import resolve_warehouse_master_table, list_warehouse_master_rows, get_warehouse_master_store_picker_rows

    if resolve_warehouse_master_table():
        out: List[Dict[str, str]] = []
        seen: set = set()
        for r in list_warehouse_master_rows(active_only=True) or []:
            loc_wh = r.get('locationcode') if r.get('locationcode') is not None else r.get('LOCATIONCODE')
            if loc_wh is not None and str(loc_wh).strip() != '':
                try:
                    if int(loc_wh) != loc:
                        continue
                except (TypeError, ValueError):
                    pass
            try:
                wid = int(r.get('warehouse_id'))
            except (TypeError, ValueError):
                continue
            if wid <= 0 or wid in seen:
                continue
            wh_code = str(r.get('warehouse_code') or '').strip()
            wh_name = str(r.get('warehouse_name') or '').strip()
            if not _matches(wh_code, wh_name, wid):
                continue
            seen.add(wid)
            out.append({'code': str(wid), 'warehouse_code': wh_code, 'name': wh_name or wh_code or str(wid)})
            if len(out) >= lim:
                break
        return out
    all_rows, _ = get_warehouse_master_store_picker_rows()
    out = []
    for r in all_rows:
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        name = str(r.get('description') or '').strip()
        try:
            wid = int(code)
        except (TypeError, ValueError):
            wid = 0
        if not _matches(code, name, wid):
            continue
        out.append({'code': code, 'warehouse_code': code, 'name': name or code})
        if len(out) >= lim:
            break
    return out


def list_warehouse_picker_rows_for_tenant(
    tenant_id: Optional[str],
    search: str = '',
    limit: int = 300,
) -> List[Dict[str, str]]:
    """Warehouse rows for user maintenance — uses tenant DB when ``tenant_id`` is set."""
    from db import get_tenant_locationcode_from_auth, is_multi_db_mode

    tid = (tenant_id or '').strip()
    prev_tid: Any = None
    switched = False
    try:
        from nexa_http import g, has_request_context
        if has_request_context() and g and is_multi_db_mode() and tid:
            prev_tid = getattr(g, 'current_tenant_id', None)
            g.current_tenant_id = tid
            switched = True
    except Exception:
        switched = False

    try:
        loc = get_tenant_locationcode_from_auth(tid) if tid else None
        if loc is None:
            try:
                from addons.sales.controllers.routes import _resolve_location_code
                loc = _resolve_location_code()
            except Exception:
                loc = 1
        return build_warehouse_picker_rows(int(loc), search=search, limit=limit)
    finally:
        if switched:
            try:
                from nexa_http import g
                g.current_tenant_id = prev_tid
            except Exception:
                pass


def warehouse_display_label(warehouse_id: Optional[int]) -> str:
    if not warehouse_id:
        return ''
    try:
        from db import get_warehouse_master_by_id
        wh = get_warehouse_master_by_id(int(warehouse_id))
    except Exception:
        wh = None
    if not wh:
        return str(warehouse_id)
    code = str(wh.get('warehouse_code') or '').strip()
    name = str(wh.get('warehouse_name') or '').strip()
    if code and name:
        return f'{code} — {name}'
    return code or name or str(warehouse_id)
