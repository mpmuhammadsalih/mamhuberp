"""Approval workflow rules, levels, and pending queue (tenant DB)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

RULE_TABLE = 'APPROVAL_WORKFLOW_RULE'
LEVEL_TABLE = 'APPROVAL_WORKFLOW_LEVEL'
QUEUE_TABLE = 'APPROVAL_WORKFLOW_QUEUE'
LOG_TABLE = 'APPROVAL_WORKFLOW_LOG'
DELEGATION_TABLE = 'APPROVAL_WORKFLOW_DELEGATION'
ESCALATION_TABLE = 'APPROVAL_WORKFLOW_ESCALATION'
RULE_SEQ = 'APPROVAL_WORKFLOW_RULE_SEQ'
QUEUE_SEQ = 'APPROVAL_WORKFLOW_QUEUE_SEQ'
LOG_SEQ = 'APPROVAL_WORKFLOW_LOG_SEQ'
DELEGATION_SEQ = 'APPROVAL_WORKFLOW_DELEGATION_SEQ'
ESCALATION_SEQ = 'APPROVAL_WORKFLOW_ESCALATION_SEQ'

TRANSACTION_TYPES: Tuple[Tuple[str, str], ...] = (
    ('PO', 'Purchase Order'),
    ('STK_ADJ', 'Stock Adjustment'),
    ('SALES_RET', 'Sales Return'),
    ('PAY_VCH', 'Payment Voucher'),
    ('PRICE_OVR', 'Price Override'),
    ('STK_TRF', 'Stock Transfer'),
    ('GRN', 'Goods Receipt'),
    ('LPO', 'Local Purchase Order'),
)

_TX_LABEL = {k: v for k, v in TRANSACTION_TYPES}


def transaction_type_label(code: str) -> str:
    c = (code or '').strip().upper()
    return _TX_LABEL.get(c, code or '')


def _resolve_location_code(session_loc: Any = None) -> int:
    loc = session_loc
    if loc is not None and str(loc).strip().isdigit():
        return int(loc)
    try:
        from db import get_location_info_by_dbkey
        info = get_location_info_by_dbkey(None)
        if info and info.get('locationcode') is not None:
            return int(info['locationcode'])
    except Exception:
        pass
    return 1


def ensure_approval_workflow_tables() -> bool:
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if not _table_exists(RULE_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {RULE_TABLE} (
                            WORKFLOW_ID      NUMBER NOT NULL,
                            LOCATIONCODE     NUMBER DEFAULT 1 NOT NULL,
                            WORKFLOW_NAME    VARCHAR2(200) NOT NULL,
                            TRANSACTION_TYPE VARCHAR2(30) NOT NULL,
                            AMOUNT_MIN       NUMBER(18,2) DEFAULT 0,
                            AMOUNT_MAX       NUMBER(18,2),
                            AMOUNT_ANY       CHAR(1) DEFAULT 'N',
                            NUM_LEVELS       NUMBER(3) DEFAULT 1,
                            STATUS           VARCHAR2(20) DEFAULT 'ACTIVE',
                            CREATED_BY       VARCHAR2(100),
                            CREATED_DATE     DATE DEFAULT SYSDATE,
                            MODIFIED_BY      VARCHAR2(100),
                            MODIFIED_DATE    DATE,
                            CONSTRAINT PK_APPROVAL_WF_RULE PRIMARY KEY (WORKFLOW_ID)
                        )
                        """
                    )
                    cur.execute(
                        f"CREATE SEQUENCE {RULE_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )
                if not _table_exists(LEVEL_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {LEVEL_TABLE} (
                            WORKFLOW_ID   NUMBER NOT NULL,
                            LEVEL_NO      NUMBER(3) NOT NULL,
                            ROLE_LABEL    VARCHAR2(120) NOT NULL,
                            APPROVER_USER VARCHAR2(100),
                            CONSTRAINT PK_APPROVAL_WF_LVL PRIMARY KEY (WORKFLOW_ID, LEVEL_NO)
                        )
                        """
                    )
                if not _table_exists(QUEUE_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {QUEUE_TABLE} (
                            QUEUE_ID          NUMBER NOT NULL,
                            LOCATIONCODE      NUMBER DEFAULT 1 NOT NULL,
                            DOCUMENT_NO       VARCHAR2(40) NOT NULL,
                            TRANSACTION_TYPE  VARCHAR2(30) NOT NULL,
                            DOCUMENT_DATE     DATE,
                            CREATED_BY        VARCHAR2(100),
                            AMOUNT            NUMBER(18,2) DEFAULT 0,
                            CURRENT_LEVEL     NUMBER(3) DEFAULT 1,
                            NUM_LEVELS        NUMBER(3) DEFAULT 1,
                            PENDING_AT        VARCHAR2(120),
                            STATUS            VARCHAR2(20) DEFAULT 'PENDING',
                            WORKFLOW_ID       NUMBER,
                            ACTION_BY         VARCHAR2(100),
                            ACTION_AT         DATE,
                            REMARKS           VARCHAR2(500),
                            CONSTRAINT PK_APPROVAL_WF_QUEUE PRIMARY KEY (QUEUE_ID)
                        )
                        """
                    )
                    cur.execute(
                        f"CREATE SEQUENCE {QUEUE_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )
                if not _table_exists(LOG_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {LOG_TABLE} (
                            LOG_ID         NUMBER NOT NULL,
                            QUEUE_ID       NUMBER,
                            LOCATIONCODE   NUMBER NOT NULL,
                            LEVEL_NO       NUMBER(3),
                            ACTION         VARCHAR2(20) NOT NULL,
                            ACTION_BY      VARCHAR2(100),
                            REMARKS        VARCHAR2(500),
                            ACTION_AT      DATE DEFAULT SYSDATE,
                            CONSTRAINT PK_APPROVAL_WF_LOG PRIMARY KEY (LOG_ID)
                        )
                        """
                    )
                    cur.execute(f"CREATE SEQUENCE {LOG_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE")
                if not _table_exists(DELEGATION_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {DELEGATION_TABLE} (
                            DELEGATION_ID   NUMBER NOT NULL,
                            LOCATIONCODE    NUMBER NOT NULL,
                            DELEGATOR_USER  VARCHAR2(100) NOT NULL,
                            DELEGATE_USER   VARCHAR2(100) NOT NULL,
                            DATE_FROM       DATE,
                            DATE_TO         DATE,
                            STATUS          VARCHAR2(20) DEFAULT 'ACTIVE',
                            REMARKS         VARCHAR2(300),
                            CONSTRAINT PK_APPROVAL_WF_DEL PRIMARY KEY (DELEGATION_ID)
                        )
                        """
                    )
                    cur.execute(f"CREATE SEQUENCE {DELEGATION_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE")
                if not _table_exists(ESCALATION_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {ESCALATION_TABLE} (
                            ESCALATION_ID    NUMBER NOT NULL,
                            LOCATIONCODE     NUMBER NOT NULL,
                            TRANSACTION_TYPE VARCHAR2(30),
                            HOURS_PENDING    NUMBER(5) DEFAULT 24,
                            ESCALATE_TO_ROLE VARCHAR2(120),
                            STATUS           VARCHAR2(20) DEFAULT 'ACTIVE',
                            CONSTRAINT PK_APPROVAL_WF_ESC PRIMARY KEY (ESCALATION_ID)
                        )
                        """
                    )
                    cur.execute(f"CREATE SEQUENCE {ESCALATION_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE")
            conn.commit()
        return _table_exists(RULE_TABLE)
    except Exception as ex:
        print(f'[ensure_approval_workflow_tables] {ex}')
        return False


def log_action(cur, queue_id: int, loc_code: int, level_no: int, action: str, user: str, remarks: str = '') -> None:
    if not _table_exists(LOG_TABLE):
        return
    cur.execute(f'SELECT {LOG_SEQ}.NEXTVAL FROM DUAL')
    lid = int(cur.fetchone()[0])
    cur.execute(
        f"""
        INSERT INTO {LOG_TABLE}
        (LOG_ID, QUEUE_ID, LOCATIONCODE, LEVEL_NO, ACTION, ACTION_BY, REMARKS, ACTION_AT)
        VALUES (:lid, :qid, :loc, :lv, :act, :usr, :rem, SYSDATE)
        """,
        {
            'lid': lid, 'qid': int(queue_id), 'loc': loc_code, 'lv': int(level_no),
            'act': (action or '')[:20], 'usr': (user or '')[:100], 'rem': (remarks or '')[:500],
        },
    )


def _amount_range_label(row: Dict[str, Any]) -> str:
    if str(row.get('amount_any') or 'N').upper() == 'Y':
        return 'Any Amount'
    mn = float(row.get('amount_min') or 0)
    mx = row.get('amount_max')
    if mx is None or str(mx).strip() == '':
        return f'{mn:,.0f} & Above'
    return f'{mn:,.0f} - {float(mx):,.0f}'


def _seed_defaults(loc_code: int, user: str) -> None:
    if not ensure_approval_workflow_tables():
        return
    rows = _safe_rows(
        f'SELECT COUNT(*) AS cnt FROM {RULE_TABLE} WHERE LOCATIONCODE = :loc',
        {'loc': loc_code},
    )
    if rows and int(rows[0].get('cnt') or rows[0].get('CNT') or 0) > 0:
        return
    samples = [
        ('Purchase Order - Level 1', 'PO', 0, 10000, 'N', 1, [
            ('Purchase Manager',),
        ]),
        ('Purchase Order - Level 2', 'PO', 10001, 20000, 'N', 2, [
            ('Purchase Manager',), ('Finance Manager',),
        ]),
        ('Purchase Order - Level 3', 'PO', 20001, None, 'N', 3, [
            ('Purchase Manager',), ('Finance Manager',), ('General Manager',),
        ]),
        ('Stock Adjustment', 'STK_ADJ', 0, 10000, 'N', 2, [
            ('Store Manager',), ('Finance Manager',),
        ]),
        ('Sales Return - Any', 'SALES_RET', 0, None, 'Y', 1, [
            ('Sales Manager',),
        ]),
        ('Payment Voucher - High', 'PAY_VCH', 5000, None, 'N', 2, [
            ('Finance Manager',), ('General Manager',),
        ]),
    ]
    for name, tx, amin, amax, any_amt, nlev, levels in samples:
        save_workflow(
            None,
            loc_code=loc_code,
            workflow_name=name,
            transaction_type=tx,
            amount_min=amin,
            amount_max=amax,
            amount_any=any_amt,
            num_levels=nlev,
            status='ACTIVE',
            levels=[{'level_no': i + 1, 'role_label': lv[0]} for i, lv in enumerate(levels)],
            user=user,
        )
    _seed_demo_pending(loc_code, user)


def _seed_demo_pending(loc_code: int, user: str) -> None:
    demos = [
        ('PO-2024-0058', 'PO', '2024-05-21', 'John Smith', 18500, 1, 2, 'Finance Manager'),
        ('SR-2024-0122', 'SALES_RET', '2024-05-21', 'Sarah Lee', 2400, 1, 1, 'Sales Manager'),
        ('PV-2024-0031', 'PAY_VCH', '2024-05-20', 'Mike Chen', 52000, 2, 2, 'General Manager'),
    ]
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for doc, tx, dt, by, amt, clvl, nlev, pending in demos:
                cur.execute(f'SELECT {QUEUE_SEQ}.NEXTVAL FROM DUAL')
                qid = int(cur.fetchone()[0])
                cur.execute(
                    f"""
                    INSERT INTO {QUEUE_TABLE}
                    (QUEUE_ID, LOCATIONCODE, DOCUMENT_NO, TRANSACTION_TYPE, DOCUMENT_DATE,
                     CREATED_BY, AMOUNT, CURRENT_LEVEL, NUM_LEVELS, PENDING_AT, STATUS)
                    VALUES (:qid, :loc, :doc, :tx, TO_DATE(:dt, 'YYYY-MM-DD'),
                            :by, :amt, :cl, :nl, :pa, 'PENDING')
                    """,
                    {
                        'qid': qid, 'loc': loc_code, 'doc': doc, 'tx': tx, 'dt': dt[:10],
                        'by': by, 'amt': amt, 'cl': clvl, 'nl': nlev, 'pa': pending,
                    },
                )
        conn.commit()


def list_workflows(loc_code: int, transaction_filter: str = '') -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    if not _table_exists(RULE_TABLE):
        return []
    where = ['LOCATIONCODE = :loc']
    params: Dict[str, Any] = {'loc': loc_code}
    tf = (transaction_filter or '').strip().upper()
    if tf and tf != 'ALL':
        where.append('TRANSACTION_TYPE = :tx')
        params['tx'] = tf
    rows = _safe_rows(
        f"""
        SELECT WORKFLOW_ID, WORKFLOW_NAME, TRANSACTION_TYPE, AMOUNT_MIN, AMOUNT_MAX,
               AMOUNT_ANY, NUM_LEVELS, STATUS, CREATED_BY, CREATED_DATE
        FROM {RULE_TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY TRANSACTION_TYPE, AMOUNT_MIN, WORKFLOW_ID
        """,
        params,
    ) or []
    out = []
    for i, r in enumerate(rows, start=1):
        out.append({
            'row_no': i,
            'workflow_id': r.get('workflow_id') or r.get('WORKFLOW_ID'),
            'workflow_name': r.get('workflow_name') or r.get('WORKFLOW_NAME'),
            'transaction_type': r.get('transaction_type') or r.get('TRANSACTION_TYPE'),
            'transaction_label': transaction_type_label(r.get('transaction_type') or r.get('TRANSACTION_TYPE')),
            'amount_min': r.get('amount_min') or r.get('AMOUNT_MIN'),
            'amount_max': r.get('amount_max') or r.get('AMOUNT_MAX'),
            'amount_any': r.get('amount_any') or r.get('AMOUNT_ANY'),
            'amount_range': _amount_range_label({
                'amount_any': r.get('amount_any') or r.get('AMOUNT_ANY'),
                'amount_min': r.get('amount_min') or r.get('AMOUNT_MIN'),
                'amount_max': r.get('amount_max') or r.get('AMOUNT_MAX'),
            }),
            'num_levels': int(r.get('num_levels') or r.get('NUM_LEVELS') or 1),
            'status': (r.get('status') or r.get('STATUS') or 'ACTIVE').upper(),
            'created_by': r.get('created_by') or r.get('CREATED_BY') or '',
            'created_date': _fmt_date(r.get('created_date') or r.get('CREATED_DATE')),
        })
    return out


def get_workflow(workflow_id: int, loc_code: int) -> Optional[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    rows = _safe_rows(
        f"""
        SELECT WORKFLOW_ID, WORKFLOW_NAME, TRANSACTION_TYPE, AMOUNT_MIN, AMOUNT_MAX,
               AMOUNT_ANY, NUM_LEVELS, STATUS, CREATED_BY, CREATED_DATE
        FROM {RULE_TABLE}
        WHERE WORKFLOW_ID = :id AND LOCATIONCODE = :loc
        """,
        {'id': int(workflow_id), 'loc': loc_code},
    )
    if not rows:
        return None
    r = rows[0]
    wid = int(r.get('workflow_id') or r.get('WORKFLOW_ID'))
    levels = _safe_rows(
        f"""
        SELECT LEVEL_NO, ROLE_LABEL, APPROVER_USER
        FROM {LEVEL_TABLE}
        WHERE WORKFLOW_ID = :id
        ORDER BY LEVEL_NO
        """,
        {'id': wid},
    ) or []
    lvl_out = []
    for lv in levels:
        lvl_out.append({
            'level_no': int(lv.get('level_no') or lv.get('LEVEL_NO') or 1),
            'role_label': lv.get('role_label') or lv.get('ROLE_LABEL') or '',
            'approver_user': lv.get('approver_user') or lv.get('APPROVER_USER') or '',
        })
    return {
        'workflow_id': wid,
        'workflow_name': r.get('workflow_name') or r.get('WORKFLOW_NAME'),
        'transaction_type': r.get('transaction_type') or r.get('TRANSACTION_TYPE'),
        'transaction_label': transaction_type_label(r.get('transaction_type') or r.get('TRANSACTION_TYPE')),
        'amount_min': float(r.get('amount_min') or r.get('AMOUNT_MIN') or 0),
        'amount_max': r.get('amount_max') if r.get('amount_max') is not None else r.get('AMOUNT_MAX'),
        'amount_any': str(r.get('amount_any') or r.get('AMOUNT_ANY') or 'N').upper(),
        'amount_range': _amount_range_label({
            'amount_any': r.get('amount_any') or r.get('AMOUNT_ANY'),
            'amount_min': r.get('amount_min') or r.get('AMOUNT_MIN'),
            'amount_max': r.get('amount_max') or r.get('AMOUNT_MAX'),
        }),
        'num_levels': int(r.get('num_levels') or r.get('NUM_LEVELS') or 1),
        'status': (r.get('status') or r.get('STATUS') or 'ACTIVE').upper(),
        'created_by': r.get('created_by') or r.get('CREATED_BY') or '',
        'created_date': _fmt_date(r.get('created_date') or r.get('CREATED_DATE')),
        'levels': lvl_out,
    }


def save_workflow(
    workflow_id: Optional[int],
    *,
    loc_code: int,
    workflow_name: str,
    transaction_type: str,
    amount_min: float,
    amount_max: Optional[float],
    amount_any: str,
    num_levels: int,
    status: str,
    levels: List[Dict[str, Any]],
    user: str,
) -> Tuple[bool, str, Optional[int]]:
    ensure_approval_workflow_tables()
    name = (workflow_name or '').strip()
    if not name:
        return False, 'Workflow name is required.', None
    tx = (transaction_type or '').strip().upper()
    if not tx:
        return False, 'Transaction type is required.', None
    nlev = max(1, min(int(num_levels or 1), 5))
    lvl_rows = levels[:nlev] if levels else [{'level_no': 1, 'role_label': 'Approver'}]
    while len(lvl_rows) < nlev:
        lvl_rows.append({'level_no': len(lvl_rows) + 1, 'role_label': f'Level {len(lvl_rows) + 1}'})
    any_f = 'Y' if str(amount_any or '').upper() in ('Y', '1', 'TRUE') else 'N'
    amn = float(amount_min or 0)
    amx = None if any_f == 'Y' else (float(amount_max) if amount_max is not None and str(amount_max).strip() != '' else None)
    st = (status or 'ACTIVE').strip().upper()
    if st not in ('ACTIVE', 'INACTIVE'):
        st = 'ACTIVE'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                wid = int(workflow_id) if workflow_id else None
                if not wid:
                    cur.execute(f'SELECT {RULE_SEQ}.NEXTVAL FROM DUAL')
                    wid = int(cur.fetchone()[0])
                    cur.execute(
                        f"""
                        INSERT INTO {RULE_TABLE}
                        (WORKFLOW_ID, LOCATIONCODE, WORKFLOW_NAME, TRANSACTION_TYPE,
                         AMOUNT_MIN, AMOUNT_MAX, AMOUNT_ANY, NUM_LEVELS, STATUS, CREATED_BY, CREATED_DATE)
                        VALUES (:id, :loc, :name, :tx, :amin, :amax, :anyf, :nl, :st, :usr, SYSDATE)
                        """,
                        {
                            'id': wid, 'loc': loc_code, 'name': name[:200], 'tx': tx[:30],
                            'amin': amn, 'amax': amx, 'anyf': any_f, 'nl': nlev, 'st': st,
                            'usr': (user or 'web')[:100],
                        },
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE {RULE_TABLE} SET
                            WORKFLOW_NAME = :name, TRANSACTION_TYPE = :tx,
                            AMOUNT_MIN = :amin, AMOUNT_MAX = :amax, AMOUNT_ANY = :anyf,
                            NUM_LEVELS = :nl, STATUS = :st,
                            MODIFIED_BY = :usr, MODIFIED_DATE = SYSDATE
                        WHERE WORKFLOW_ID = :id AND LOCATIONCODE = :loc
                        """,
                        {
                            'id': wid, 'loc': loc_code, 'name': name[:200], 'tx': tx[:30],
                            'amin': amn, 'amax': amx, 'anyf': any_f, 'nl': nlev, 'st': st,
                            'usr': (user or 'web')[:100],
                        },
                    )
                    cur.execute(f'DELETE FROM {LEVEL_TABLE} WHERE WORKFLOW_ID = :id', {'id': wid})
                for lv in lvl_rows[:nlev]:
                    lno = int(lv.get('level_no') or 1)
                    rl = str(lv.get('role_label') or f'Level {lno}')[:120]
                    au = str(lv.get('approver_user') or '')[:100] or None
                    cur.execute(
                        f"""
                        INSERT INTO {LEVEL_TABLE}
                        (WORKFLOW_ID, LEVEL_NO, ROLE_LABEL, APPROVER_USER)
                        VALUES (:id, :ln, :rl, :au)
                        """,
                        {'id': wid, 'ln': lno, 'rl': rl, 'au': au},
                    )
            conn.commit()
        return True, '', wid
    except Exception as ex:
        return False, str(ex), None


def delete_workflow(workflow_id: int, loc_code: int) -> Tuple[bool, str]:
    ensure_approval_workflow_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM {LEVEL_TABLE} WHERE WORKFLOW_ID = :id',
                    {'id': int(workflow_id)},
                )
                cur.execute(
                    f'DELETE FROM {RULE_TABLE} WHERE WORKFLOW_ID = :id AND LOCATIONCODE = :loc',
                    {'id': int(workflow_id), 'loc': loc_code},
                )
            conn.commit()
        return True, ''
    except Exception as ex:
        return False, str(ex)


def list_pending(loc_code: int, limit: int = 12) -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    if not _table_exists(QUEUE_TABLE):
        return []
    cap = min(max(int(limit or 12), 1), 100)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT QUEUE_ID, DOCUMENT_NO, TRANSACTION_TYPE,
                   TO_CHAR(DOCUMENT_DATE, 'DD Mon YYYY', 'NLS_DATE_LANGUAGE=ENGLISH') AS doc_date,
                   CREATED_BY, AMOUNT, CURRENT_LEVEL, NUM_LEVELS, PENDING_AT, STATUS
            FROM {QUEUE_TABLE}
            WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'PENDING'
            ORDER BY DOCUMENT_DATE DESC, QUEUE_ID DESC
        ) WHERE ROWNUM <= :cap
        """,
        {'loc': loc_code, 'cap': cap},
    ) or []
    out = []
    for r in rows:
        out.append({
            'queue_id': r.get('queue_id') or r.get('QUEUE_ID'),
            'document_no': r.get('document_no') or r.get('DOCUMENT_NO'),
            'transaction_type': r.get('transaction_type') or r.get('TRANSACTION_TYPE'),
            'transaction_label': transaction_type_label(r.get('transaction_type') or r.get('TRANSACTION_TYPE')),
            'document_date': r.get('doc_date') or r.get('DOC_DATE') or '',
            'created_by': r.get('created_by') or r.get('CREATED_BY') or '',
            'amount': float(r.get('amount') or r.get('AMOUNT') or 0),
            'current_level': int(r.get('current_level') or r.get('CURRENT_LEVEL') or 1),
            'pending_at': r.get('pending_at') or r.get('PENDING_AT') or '',
        })
    return out


def count_pending(loc_code: int) -> int:
    rows = _safe_rows(
        f"SELECT COUNT(*) AS cnt FROM {QUEUE_TABLE} WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'PENDING'",
        {'loc': loc_code},
    )
    return int((rows[0].get('cnt') or rows[0].get('CNT') or 0) if rows else 0)


def count_awaiting_others(loc_code: int) -> int:
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {QUEUE_TABLE}
        WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'PENDING' AND CURRENT_LEVEL > 1
        """,
        {'loc': loc_code},
    )
    return int((rows[0].get('cnt') or rows[0].get('CNT') or 0) if rows else 0)


def count_approved_today(loc_code: int) -> int:
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {QUEUE_TABLE}
        WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'APPROVED'
          AND TRUNC(ACTION_AT) = TRUNC(SYSDATE)
        """,
        {'loc': loc_code},
    )
    return int((rows[0].get('cnt') or rows[0].get('CNT') or 0) if rows else 0)


def count_active_workflows(loc_code: int) -> int:
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {RULE_TABLE}
        WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'ACTIVE'
        """,
        {'loc': loc_code},
    )
    return int((rows[0].get('cnt') or rows[0].get('CNT') or 0) if rows else 0)


def queue_action(queue_id: int, loc_code: int, action: str, user: str, remarks: str = '') -> Tuple[bool, str]:
    from addons.approval_workflow.approval_workflow_engine import process_queue_action
    ok, err, _done = process_queue_action(queue_id, loc_code, action, user, remarks)
    return ok, err


def list_history(loc_code: int, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    cap = min(max(int(limit or 50), 1), 200)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT q.DOCUMENT_NO, q.TRANSACTION_TYPE, q.AMOUNT,
                   TO_CHAR(q.ACTION_AT, 'DD Mon YYYY HH24:MI') AS action_at,
                   q.STATUS, q.ACTION_BY, q.REMARKS,
                   l.LEVEL_NO, l.ACTION AS log_action, l.ACTION_BY AS log_by
            FROM {QUEUE_TABLE} q
            LEFT JOIN {LOG_TABLE} l ON l.QUEUE_ID = q.QUEUE_ID
            WHERE q.LOCATIONCODE = :loc AND q.STATUS IN ('APPROVED', 'REJECTED')
            ORDER BY q.ACTION_AT DESC NULLS LAST, l.ACTION_AT DESC
        ) WHERE ROWNUM <= :cap
        """,
        {'loc': loc_code, 'cap': cap},
    ) or []
    out = []
    for r in rows:
        out.append({
            'document_no': r.get('document_no') or r.get('DOCUMENT_NO'),
            'transaction_label': transaction_type_label(r.get('transaction_type') or r.get('TRANSACTION_TYPE')),
            'amount': float(r.get('amount') or r.get('AMOUNT') or 0),
            'action_at': r.get('action_at') or r.get('ACTION_AT') or '',
            'status': r.get('status') or r.get('STATUS'),
            'action_by': r.get('action_by') or r.get('ACTION_BY') or '',
            'remarks': r.get('remarks') or r.get('REMARKS') or '',
            'level_no': r.get('level_no') or r.get('LEVEL_NO'),
            'log_action': r.get('log_action') or r.get('LOG_ACTION'),
        })
    return out


def list_my_approvals(loc_code: int, user: str, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    u = (user or '').strip().lower()
    cap = min(max(int(limit or 50), 1), 200)
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT QUEUE_ID, DOCUMENT_NO, TRANSACTION_TYPE, AMOUNT, STATUS, ACTION_BY,
                   TO_CHAR(ACTION_AT, 'DD Mon YYYY') AS action_at
            FROM {QUEUE_TABLE}
            WHERE LOCATIONCODE = :loc AND LOWER(ACTION_BY) = :u
              AND STATUS IN ('APPROVED', 'REJECTED')
            ORDER BY ACTION_AT DESC
        ) WHERE ROWNUM <= :cap
        """,
        {'loc': loc_code, 'u': u, 'cap': cap},
    ) or []
    return [
        {
            'document_no': r.get('document_no') or r.get('DOCUMENT_NO'),
            'transaction_label': transaction_type_label(r.get('transaction_type') or r.get('TRANSACTION_TYPE')),
            'amount': float(r.get('amount') or r.get('AMOUNT') or 0),
            'status': r.get('status') or r.get('STATUS'),
            'action_at': r.get('action_at') or '',
        }
        for r in rows
    ]


def list_delegations(loc_code: int) -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    if not _table_exists(DELEGATION_TABLE):
        return []
    rows = _safe_rows(
        f"""
        SELECT DELEGATION_ID, DELEGATOR_USER, DELEGATE_USER,
               TO_CHAR(DATE_FROM, 'YYYY-MM-DD') AS date_from,
               TO_CHAR(DATE_TO, 'YYYY-MM-DD') AS date_to,
               STATUS, REMARKS
        FROM {DELEGATION_TABLE}
        WHERE LOCATIONCODE = :loc
        ORDER BY DELEGATION_ID DESC
        """,
        {'loc': loc_code},
    ) or []
    return [
        {
            'delegation_id': r.get('delegation_id') or r.get('DELEGATION_ID'),
            'delegator_user': r.get('delegator_user') or r.get('DELEGATOR_USER'),
            'delegate_user': r.get('delegate_user') or r.get('DELEGATE_USER'),
            'date_from': r.get('date_from') or '',
            'date_to': r.get('date_to') or '',
            'status': r.get('status') or r.get('STATUS'),
            'remarks': r.get('remarks') or r.get('REMARKS') or '',
        }
        for r in rows
    ]


def save_delegation(loc_code: int, data: Dict[str, Any]) -> Tuple[bool, str]:
    ensure_approval_workflow_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {DELEGATION_SEQ}.NEXTVAL FROM DUAL')
                did = int(cur.fetchone()[0])
                cur.execute(
                    f"""
                    INSERT INTO {DELEGATION_TABLE}
                    (DELEGATION_ID, LOCATIONCODE, DELEGATOR_USER, DELEGATE_USER,
                     DATE_FROM, DATE_TO, STATUS, REMARKS)
                    VALUES (:id, :loc, :du, :dg, TO_DATE(:df, 'YYYY-MM-DD'), TO_DATE(:dt, 'YYYY-MM-DD'), 'ACTIVE', :rem)
                    """,
                    {
                        'id': did, 'loc': loc_code,
                        'du': (data.get('delegator_user') or '')[:100],
                        'dg': (data.get('delegate_user') or '')[:100],
                        'df': (data.get('date_from') or '')[:10] or None,
                        'dt': (data.get('date_to') or '')[:10] or None,
                        'rem': (data.get('remarks') or '')[:300],
                    },
                )
            conn.commit()
        return True, ''
    except Exception as ex:
        return False, str(ex)


def list_escalations(loc_code: int) -> List[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    if not _table_exists(ESCALATION_TABLE):
        return []
    rows = _safe_rows(
        f"""
        SELECT ESCALATION_ID, TRANSACTION_TYPE, HOURS_PENDING, ESCALATE_TO_ROLE, STATUS
        FROM {ESCALATION_TABLE}
        WHERE LOCATIONCODE = :loc
        ORDER BY ESCALATION_ID
        """,
        {'loc': loc_code},
    ) or []
    return [
        {
            'escalation_id': r.get('escalation_id') or r.get('ESCALATION_ID'),
            'transaction_type': r.get('transaction_type') or r.get('TRANSACTION_TYPE') or 'ALL',
            'transaction_label': transaction_type_label(r.get('transaction_type') or 'ALL') if (r.get('transaction_type') or 'ALL') != 'ALL' else 'All',
            'hours_pending': int(r.get('hours_pending') or r.get('HOURS_PENDING') or 24),
            'escalate_to_role': r.get('escalate_to_role') or r.get('ESCALATE_TO_ROLE') or '',
            'status': r.get('status') or r.get('STATUS'),
        }
        for r in rows
    ]


def save_escalation(loc_code: int, data: Dict[str, Any]) -> Tuple[bool, str]:
    ensure_approval_workflow_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {ESCALATION_SEQ}.NEXTVAL FROM DUAL')
                eid = int(cur.fetchone()[0])
                tx = (data.get('transaction_type') or 'ALL').strip().upper()[:30]
                cur.execute(
                    f"""
                    INSERT INTO {ESCALATION_TABLE}
                    (ESCALATION_ID, LOCATIONCODE, TRANSACTION_TYPE, HOURS_PENDING, ESCALATE_TO_ROLE, STATUS)
                    VALUES (:id, :loc, :tx, :hrs, :role, 'ACTIVE')
                    """,
                    {
                        'id': eid, 'loc': loc_code, 'tx': tx,
                        'hrs': int(data.get('hours_pending') or 24),
                        'role': (data.get('escalate_to_role') or '')[:120],
                    },
                )
            conn.commit()
        return True, ''
    except Exception as ex:
        return False, str(ex)


def count_my_approvals_today(loc_code: int, user: str) -> int:
    u = (user or '').strip().lower()
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {QUEUE_TABLE}
        WHERE LOCATIONCODE = :loc AND LOWER(ACTION_BY) = :u
          AND STATUS IN ('APPROVED', 'REJECTED') AND TRUNC(ACTION_AT) = TRUNC(SYSDATE)
        """,
        {'loc': loc_code, 'u': u},
    )
    return int((rows[0].get('cnt') or 0) if rows else 0)


def build_dashboard_payload(loc_code: int, user: str, transaction_filter: str = '') -> Dict[str, Any]:
    _seed_defaults(loc_code, user)
    workflows = list_workflows(loc_code, transaction_filter)
    pending = list_pending(loc_code, 50)
    selected = workflows[0] if workflows else None
    detail = get_workflow(int(selected['workflow_id']), loc_code) if selected else None
    return {
        'kpis': {
            'active_workflows': count_active_workflows(loc_code),
            'pending_approvals': count_pending(loc_code),
            'awaiting_others': count_awaiting_others(loc_code),
            'approved_today': count_approved_today(loc_code),
            'my_approvals_today': count_my_approvals_today(loc_code, user),
        },
        'workflows': workflows,
        'pending': pending,
        'selected_workflow': detail,
        'transaction_types': [{'code': c, 'label': l} for c, l in TRANSACTION_TYPES],
        'history': list_history(loc_code, 30),
        'my_approvals': list_my_approvals(loc_code, user, 30),
        'delegations': list_delegations(loc_code),
        'escalations': list_escalations(loc_code),
    }


def _fmt_date(val: Any) -> str:
    if val is None:
        return ''
    if hasattr(val, 'strftime'):
        return val.strftime('%d %b %Y')
    return str(val)[:20]
