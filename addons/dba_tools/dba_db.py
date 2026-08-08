"""DBA helpers: list tables, inspect Oracle lock status, and release table locks.

These helpers inspect the *tenant / business* database (``_get_connection()``),
not the auth database. Lock information comes from Oracle dynamic views
(``v$locked_object``, ``v$session``) and requires the connected user to have
SELECT on those views; releasing a lock requires ALTER SYSTEM privilege.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db.oracle_driver import cx_Oracle

from db import _get_connection

# Oracle TM lock modes (v$locked_object.locked_mode)
_LOCK_MODE_LABELS = {
    0: 'None',
    1: 'Null',
    2: 'Row-S (SS)',
    3: 'Row-X (SX)',
    4: 'Share (S)',
    5: 'S/Row-X (SSX)',
    6: 'Exclusive (X)',
}


def lock_mode_label(mode: Any) -> str:
    try:
        return _LOCK_MODE_LABELS.get(int(mode), str(mode))
    except (TypeError, ValueError):
        return str(mode) if mode is not None else ''


def _rows(cur) -> List[Dict[str, Any]]:
    cols = [c[0].lower() for c in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def list_user_tables() -> List[Dict[str, Any]]:
    """Return tables owned by the connected schema (name, row estimate, last analyzed)."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name AS table_name,
                       NVL(num_rows, 0) AS num_rows,
                       last_analyzed AS last_analyzed
                FROM user_tables
                ORDER BY table_name
                """
            )
            return _rows(cur)


def get_lock_details() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Rows of currently locked tables (one per session/lock). Returns (rows, error)."""
    query = """
        SELECT o.object_name          AS table_name,
               lo.session_id          AS sid,
               s.serial#              AS serial_no,
               lo.locked_mode         AS locked_mode,
               s.username             AS lock_username,
               s.osuser               AS osuser,
               s.machine              AS machine,
               s.program              AS program,
               s.status               AS session_status,
               s.blocking_session     AS blocking_session,
               s.seconds_in_wait      AS seconds_in_wait,
               s.sql_id               AS sql_id
        FROM v$locked_object lo
        JOIN all_objects o ON o.object_id = lo.object_id
        LEFT JOIN v$session s ON s.sid = lo.session_id
        WHERE o.object_type = 'TABLE'
        ORDER BY o.object_name, lo.session_id
    """
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return _rows(cur), None
    except cx_Oracle.DatabaseError as e:
        return [], str(e).strip()


def list_tables_with_lock_status(search: str = '') -> Dict[str, Any]:
    """Combine the table list with lock information keyed by table name."""
    tables = list_user_tables()
    lock_rows, lock_error = get_lock_details()

    locks_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for lr in lock_rows:
        name = str(lr.get('table_name') or '').upper()
        entry = {
            'sid': lr.get('sid'),
            'serial_no': lr.get('serial_no'),
            'locked_mode': lr.get('locked_mode'),
            'locked_mode_label': lock_mode_label(lr.get('locked_mode')),
            'lock_username': lr.get('lock_username'),
            'osuser': lr.get('osuser'),
            'machine': lr.get('machine'),
            'program': lr.get('program'),
            'session_status': lr.get('session_status'),
            'blocking_session': lr.get('blocking_session'),
            'seconds_in_wait': lr.get('seconds_in_wait'),
            'sql_id': lr.get('sql_id'),
        }
        locks_by_table.setdefault(name, []).append(entry)

    term = str(search or '').strip().upper()
    out: List[Dict[str, Any]] = []
    for t in tables:
        name = str(t.get('table_name') or '')
        if term and term not in name.upper():
            continue
        lockers = locks_by_table.get(name.upper(), [])
        out.append({
            'table_name': name,
            'num_rows': int(t.get('num_rows') or 0),
            'last_analyzed': t.get('last_analyzed').strftime('%Y-%m-%d %H:%M') if t.get('last_analyzed') else '',
            'locked': bool(lockers),
            'lock_count': len(lockers),
            'lockers': lockers,
        })

    # Locked tables that are not in user_tables (e.g. other schema) — surface anyway.
    known = {r['table_name'].upper() for r in out}
    for name, lockers in locks_by_table.items():
        if name in known:
            continue
        if term and term not in name:
            continue
        out.append({
            'table_name': name,
            'num_rows': 0,
            'last_analyzed': '',
            'locked': True,
            'lock_count': len(lockers),
            'lockers': lockers,
        })

    out.sort(key=lambda r: (not r['locked'], r['table_name']))
    locked_total = sum(1 for r in out if r['locked'])
    return {
        'tables': out,
        'total': len(out),
        'locked_total': locked_total,
        'lock_error': lock_error,
    }


def _sessions_locking_table(cur, table_name: str) -> List[Tuple[int, int]]:
    """Return (sid, serial#) pairs holding a TM lock on ``table_name``."""
    cur.execute(
        """
        SELECT lo.session_id AS sid, s.serial# AS serial_no
        FROM v$locked_object lo
        JOIN all_objects o ON o.object_id = lo.object_id
        LEFT JOIN v$session s ON s.sid = lo.session_id
        WHERE o.object_type = 'TABLE'
          AND UPPER(o.object_name) = :tname
        """,
        {'tname': str(table_name or '').strip().upper()},
    )
    pairs: List[Tuple[int, int]] = []
    for row in cur.fetchall():
        sid, serial_no = row[0], row[1]
        if sid is not None and serial_no is not None:
            pairs.append((int(sid), int(serial_no)))
    return pairs


def unlock_table(table_name: str) -> Dict[str, Any]:
    """Release locks on a table by killing the sessions that hold them.

    Returns a summary dict with per-session outcomes. Requires ALTER SYSTEM.
    """
    name = str(table_name or '').strip().upper()
    if not name:
        return {'success': False, 'error': 'Table name is required.', 'actions': []}

    actions: List[Dict[str, Any]] = []
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                sessions = _sessions_locking_table(cur, name)
                if not sessions:
                    return {
                        'success': True,
                        'table_name': name,
                        'message': f'No active locks found on {name}.',
                        'killed': 0,
                        'actions': [],
                    }
                for sid, serial_no in sessions:
                    ident = f'{sid},{serial_no}'
                    outcome = {'session': ident, 'killed': False, 'detail': ''}
                    try:
                        cur.execute(f"ALTER SYSTEM KILL SESSION '{ident}' IMMEDIATE")
                        outcome['killed'] = True
                        outcome['detail'] = 'Killed'
                    except cx_Oracle.DatabaseError as ke:
                        err = str(ke).strip()
                        # ORA-00030/ORA-00031: session already gone / marked for kill
                        if 'ORA-00030' in err or 'ORA-00031' in err:
                            outcome['killed'] = True
                            outcome['detail'] = 'Session already terminated/marked'
                        else:
                            # Fall back to a forced disconnect of the server process.
                            try:
                                cur.execute(
                                    f"ALTER SYSTEM DISCONNECT SESSION '{ident}' IMMEDIATE"
                                )
                                outcome['killed'] = True
                                outcome['detail'] = 'Disconnected'
                            except cx_Oracle.DatabaseError as de:
                                outcome['detail'] = str(de).strip()
                    actions.append(outcome)
        killed = sum(1 for a in actions if a['killed'])
        success = killed > 0
        message = (
            f'Released {killed} of {len(actions)} locking session(s) on {name}.'
            if success else f'Could not release locks on {name}.'
        )
        return {
            'success': success,
            'table_name': name,
            'message': message,
            'killed': killed,
            'actions': actions,
        }
    except cx_Oracle.DatabaseError as e:
        return {'success': False, 'error': str(e).strip(), 'table_name': name, 'actions': actions}
