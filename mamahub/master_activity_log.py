"""Per-tenant audit trail for Master / inventory-master CRUD (Oracle tenant DB).

ENTITY column examples: customer, supplier, salesman, route, customer_category, employee,
session_master; item_category_master, item_brand_master, unit_of_measurement, item_property, item_origin;
itemmaster_central (HO Itemmaster Central save/sync/remap/delete); itemmaster_branch (branch Item Master screen saves);
temporary_collection (Temporary Collection save / bulk save pending).
"""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
MASTER_ACT_TABLE = 'NEXA_MASTER_ACTIVITY_LOG'
MASTER_ACT_SEQ = 'NEXA_MASTER_ACT_SEQ'

def ensure_master_activity_log_table() -> bool:
    """Create sequence + table if missing (Oracle)."""
    from db import _TABLE_EXISTS_CACHE, _get_connection, _table_exists
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :n', {'n': MASTER_ACT_SEQ})
                if cur.fetchone()[0] == 0:
                    cur.execute(f'CREATE SEQUENCE {MASTER_ACT_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE')
                    conn.commit()
        if not _table_exists(MASTER_ACT_TABLE):
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f'\n                        CREATE TABLE {MASTER_ACT_TABLE} (\n                            LOG_ID      NUMBER PRIMARY KEY,\n                            ACTION      VARCHAR2(32)  NOT NULL,\n                            ENTITY      VARCHAR2(96)  NOT NULL,\n                            SUMMARY     VARCHAR2(500),\n                            USERNAME    VARCHAR2(128),\n                            LOGGED_AT   DATE DEFAULT SYSDATE NOT NULL,\n                            DETAIL_JSON CLOB\n                        )\n                        ')
                    conn.commit()
        _TABLE_EXISTS_CACHE.pop(MASTER_ACT_TABLE, None)
        return True
    except Exception as e:
        print(f'[ERROR ensure_master_activity_log_table] {e}')
        return False

def append_master_activity(*, username: Optional[str], action: str, entity: str, summary: str, detail: Optional[Dict[str, Any]]=None) -> None:
    """Append one row (best-effort; failures are logged to console only)."""
    try:
        ensure_master_activity_log_table()
        from db import _get_connection
        act = (action or '')[:32]
        ent = (entity or '')[:96]
        summ = (summary or '')[:500]
        uname = (username or '')[:128]
        payload = json.dumps(detail or {}, default=str)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'\n                    INSERT INTO {MASTER_ACT_TABLE}\n                        (LOG_ID, ACTION, ENTITY, SUMMARY, USERNAME, DETAIL_JSON)\n                    VALUES ({MASTER_ACT_SEQ}.NEXTVAL, :act, :ent, :summ, :uname, :dj)\n                    ', {'act': act, 'ent': ent, 'summ': summ, 'uname': uname, 'dj': payload})
            conn.commit()
    except Exception as e:
        print(f'[WARN append_master_activity] {e}')

def fetch_master_activity_log(*, entity_prefix: Optional[str]=None, entity_exact: Optional[str]=None, limit: int=300) -> List[Dict[str, Any]]:
    """Recent rows newest first."""
    from db import _safe_rows
    if not ensure_master_activity_log_table():
        return []
    lim = max(1, min(int(limit or 300), 2000))
    if entity_exact and str(entity_exact).strip():
        ex = str(entity_exact).strip()[:96]
        sql = f'\n            SELECT * FROM (\n                SELECT LOG_ID, ACTION, ENTITY, SUMMARY, USERNAME, LOGGED_AT, DETAIL_JSON\n                FROM {MASTER_ACT_TABLE}\n                WHERE ENTITY = :ex\n                ORDER BY LOGGED_AT DESC, LOG_ID DESC\n            ) WHERE ROWNUM <= :lim\n        '
        rows = _safe_rows(sql, {'ex': ex, 'lim': lim})
    elif entity_prefix and str(entity_prefix).strip():
        pfx = str(entity_prefix).strip()[:96] + '%'
        sql = f'\n            SELECT * FROM (\n                SELECT LOG_ID, ACTION, ENTITY, SUMMARY, USERNAME, LOGGED_AT, DETAIL_JSON\n                FROM {MASTER_ACT_TABLE}\n                WHERE ENTITY LIKE :pfx\n                ORDER BY LOGGED_AT DESC, LOG_ID DESC\n            ) WHERE ROWNUM <= :lim\n        '
        rows = _safe_rows(sql, {'pfx': pfx, 'lim': lim})
    else:
        sql = f'\n            SELECT * FROM (\n                SELECT LOG_ID, ACTION, ENTITY, SUMMARY, USERNAME, LOGGED_AT, DETAIL_JSON\n                FROM {MASTER_ACT_TABLE}\n                ORDER BY LOGGED_AT DESC, LOG_ID DESC\n            ) WHERE ROWNUM <= :lim\n        '
        rows = _safe_rows(sql, {'lim': lim})
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        dj = r.get('detail_json')
        parsed: Optional[Dict[str, Any]] = None
        if isinstance(dj, str) and dj.strip():
            try:
                parsed = json.loads(dj)
            except Exception:
                parsed = None
        out.append({'log_id': r.get('log_id'), 'action': r.get('action'), 'entity': r.get('entity'), 'summary': r.get('summary'), 'username': r.get('username'), 'logged_at': r.get('logged_at'), 'detail': parsed})
    return out
