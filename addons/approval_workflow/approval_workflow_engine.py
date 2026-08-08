"""Enqueue documents, multi-level approval, and post-approval hooks."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from addons.approval_workflow.approval_workflow_db import (
    LOG_TABLE,
    ensure_approval_workflow_tables,
    get_workflow,
    log_action,
    transaction_type_label,
    _resolve_location_code,
)
from db import _get_connection, _safe_rows, _table_exists

QUEUE_TABLE = 'APPROVAL_WORKFLOW_QUEUE'


def document_no_for(tx_type: str, doc_no: int | str) -> str:
    tx = (tx_type or '').strip().upper()
    n = str(doc_no).strip()
    if tx == 'STK_ADJ':
        nu = n.upper()
        if nu.startswith('SA-'):
            return nu
        return f'SA-{n}'
    if tx == 'LPO':
        return f'LPO-{n}'
    if tx == 'GRN':
        return f'GRN-{n}'
    if tx == 'PO':
        return f'PO-{n}'
    return f'{tx}-{n}'


def parse_document_no(document_no: str) -> Tuple[str, str]:
    s = (document_no or '').strip().upper()
    if s.startswith('SA-'):
        return 'STK_ADJ', s[3:]
    m = re.match(r'^([A-Z0-9_]+)-(.+)$', s)
    if m:
        tx = m.group(1)
        if tx == 'PO':
            tx = 'LPO'
        return tx, m.group(2)
    return s, ''


def find_matching_workflow(loc_code: int, transaction_type: str, amount: float) -> Optional[Dict[str, Any]]:
    ensure_approval_workflow_tables()
    tx = (transaction_type or '').strip().upper()
    rows = _safe_rows(
        f"""
        SELECT WORKFLOW_ID, WORKFLOW_NAME, TRANSACTION_TYPE, AMOUNT_MIN, AMOUNT_MAX,
               AMOUNT_ANY, NUM_LEVELS, STATUS
        FROM APPROVAL_WORKFLOW_RULE
        WHERE LOCATIONCODE = :loc AND UPPER(STATUS) = 'ACTIVE'
          AND TRANSACTION_TYPE = :tx
        ORDER BY AMOUNT_MIN DESC, WORKFLOW_ID
        """,
        {'loc': loc_code, 'tx': tx},
    ) or []
    amt = float(amount or 0)
    for r in rows:
        any_f = str(r.get('amount_any') or r.get('AMOUNT_ANY') or 'N').upper() == 'Y'
        amin = float(r.get('amount_min') or r.get('AMOUNT_MIN') or 0)
        amax = r.get('amount_max') if r.get('amount_max') is not None else r.get('AMOUNT_MAX')
        if any_f:
            wf = get_workflow(int(r.get('workflow_id') or r.get('WORKFLOW_ID')), loc_code)
            return wf
        if amax is None or str(amax).strip() == '':
            if amt >= amin:
                return get_workflow(int(r.get('workflow_id') or r.get('WORKFLOW_ID')), loc_code)
        else:
            if amin <= amt <= float(amax):
                return get_workflow(int(r.get('workflow_id') or r.get('WORKFLOW_ID')), loc_code)
    return None


def requires_approval(loc_code: int, transaction_type: str, amount: float) -> bool:
    return find_matching_workflow(loc_code, transaction_type, amount) is not None


def _level_role(workflow: Dict[str, Any], level_no: int) -> str:
    for lv in workflow.get('levels') or []:
        if int(lv.get('level_no') or 0) == int(level_no):
            return str(lv.get('role_label') or '')
    return f'Level {level_no}'


def enqueue_document(
    *,
    loc_code: int,
    transaction_type: str,
    doc_no: int | str,
    amount: float,
    created_by: str,
    document_date: Optional[str] = None,
    workflow: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Optional[int]]:
    ensure_approval_workflow_tables()
    wf = workflow or find_matching_workflow(loc_code, transaction_type, amount)
    if not wf:
        return False, 'No matching workflow.', None
    doc_key = document_no_for(transaction_type, doc_no)
    wid = int(wf['workflow_id'])
    nlev = int(wf.get('num_levels') or 1)
    pending_at = _level_role(wf, 1)
    dt = (document_date or datetime.now().strftime('%Y-%m-%d'))[:10]
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {QUEUE_TABLE}
                    WHERE LOCATIONCODE = :loc AND DOCUMENT_NO = :doc
                      AND UPPER(STATUS) = 'PENDING'
                    """,
                    {'loc': loc_code, 'doc': doc_key},
                )
                cur.execute('SELECT APPROVAL_WORKFLOW_QUEUE_SEQ.NEXTVAL FROM DUAL')
                qid = int(cur.fetchone()[0])
                cur.execute(
                    f"""
                    INSERT INTO {QUEUE_TABLE}
                    (QUEUE_ID, LOCATIONCODE, DOCUMENT_NO, TRANSACTION_TYPE, DOCUMENT_DATE,
                     CREATED_BY, AMOUNT, CURRENT_LEVEL, NUM_LEVELS, PENDING_AT, STATUS, WORKFLOW_ID)
                    VALUES (:qid, :loc, :doc, :tx, TO_DATE(:dt, 'YYYY-MM-DD'),
                            :by, :amt, 1, :nl, :pa, 'PENDING', :wid)
                    """,
                    {
                        'qid': qid, 'loc': loc_code, 'doc': doc_key,
                        'tx': (transaction_type or '').upper()[:30], 'dt': dt,
                        'by': (created_by or 'web')[:100], 'amt': float(amount or 0),
                        'nl': nlev, 'pa': pending_at[:120], 'wid': wid,
                    },
                )
                log_action(cur, qid, loc_code, 1, 'SUBMIT', created_by, 'Submitted for approval')
            conn.commit()
        return True, '', qid
    except Exception as ex:
        return False, str(ex), None


def remove_pending_enqueue(
    loc_code: int,
    transaction_type: str,
    doc_no: int | str,
    *,
    queue_id: Optional[int] = None,
) -> None:
    """Drop a pending approval queue row (e.g. when document save failed after enqueue)."""
    ensure_approval_workflow_tables()
    doc_key = document_no_for(transaction_type, doc_no)
    params: Dict[str, Any] = {'loc': loc_code, 'doc': doc_key}
    where = [
        'LOCATIONCODE = :loc',
        'DOCUMENT_NO = :doc',
        "UPPER(STATUS) = 'PENDING'",
    ]
    if queue_id:
        where.append('QUEUE_ID = :qid')
        params['qid'] = int(queue_id)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {QUEUE_TABLE} WHERE {' AND '.join(where)}",
                    params,
                )
            conn.commit()
    except Exception:
        pass


def is_document_approved(loc_code: int, transaction_type: str, doc_no: int | str) -> bool:
    ensure_approval_workflow_tables()
    doc_key = document_no_for(transaction_type, doc_no)
    rows = _safe_rows(
        f"""
        SELECT STATUS FROM {QUEUE_TABLE}
        WHERE LOCATIONCODE = :loc AND DOCUMENT_NO = :doc
        ORDER BY QUEUE_ID DESC
        """,
        {'loc': loc_code, 'doc': doc_key},
    )
    if not rows:
        return True
    st = str(rows[0].get('status') or rows[0].get('STATUS') or '').upper()
    return st == 'APPROVED'


def get_pending_queue_row(loc_code: int, transaction_type: str, doc_no: int | str) -> Optional[Dict[str, Any]]:
    doc_key = document_no_for(transaction_type, doc_no)
    rows = _safe_rows(
        f"""
        SELECT QUEUE_ID, STATUS, CURRENT_LEVEL, NUM_LEVELS
        FROM {QUEUE_TABLE}
        WHERE LOCATIONCODE = :loc AND DOCUMENT_NO = :doc AND UPPER(STATUS) = 'PENDING'
        ORDER BY QUEUE_ID DESC
        """,
        {'loc': loc_code, 'doc': doc_key},
    )
    return rows[0] if rows else None


def finalize_approved_document(transaction_type: str, document_no: str, loc_code: int) -> Optional[str]:
    tx, raw = parse_document_no(document_no)
    if tx == 'STK_ADJ' or transaction_type == 'STK_ADJ':
        from db.inventory_doc_numbers import parse_adjno_from_request, adjno_is_valid
        adj_no = parse_adjno_from_request(raw)
        if not adjno_is_valid(adj_no):
            return 'Invalid adjustment number.'
        from addons.purchase.stock_adjustment_approval import post_stock_adjustment_after_approval
        return post_stock_adjustment_after_approval(adj_no, loc_code)
    return None


def process_queue_action(
    queue_id: int,
    loc_code: int,
    action: str,
    user: str,
    remarks: str = '',
) -> Tuple[bool, str, bool]:
    """
    Approve/reject with multi-level support. Returns (ok, error, fully_completed).
    """
    act = (action or '').strip().upper()
    if act not in ('APPROVE', 'REJECT'):
        return False, 'Invalid action.', False
    ensure_approval_workflow_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT QUEUE_ID, DOCUMENT_NO, TRANSACTION_TYPE, CURRENT_LEVEL, NUM_LEVELS,
                           WORKFLOW_ID, STATUS
                    FROM {QUEUE_TABLE}
                    WHERE QUEUE_ID = :qid AND LOCATIONCODE = :loc AND UPPER(STATUS) = 'PENDING'
                    """,
                    {'qid': int(queue_id), 'loc': loc_code},
                )
                row = cur.fetchone()
                if not row:
                    return False, 'Document not found or already actioned.', False
                cols = [c[0].lower() for c in cur.description or []]
                rec = dict(zip(cols, row))
                if act == 'REJECT':
                    cur.execute(
                        f"""
                        UPDATE {QUEUE_TABLE} SET STATUS = 'REJECTED', ACTION_BY = :u, ACTION_AT = SYSDATE, REMARKS = :r
                        WHERE QUEUE_ID = :qid
                        """,
                        {'u': user[:100], 'r': (remarks or '')[:500], 'qid': int(queue_id)},
                    )
                    log_action(cur, int(queue_id), loc_code, int(rec.get('current_level') or 1), 'REJECT', user, remarks)
                    conn.commit()
                    return True, '', False
                cl = int(rec.get('current_level') or 1)
                nl = int(rec.get('num_levels') or 1)
                wid = int(rec.get('workflow_id') or 0)
                wf = get_workflow(wid, loc_code) if wid else None
                log_action(cur, int(queue_id), loc_code, cl, 'APPROVE', user, remarks)
                if cl < nl:
                    ncl = cl + 1
                    pa = _level_role(wf or {}, ncl)
                    cur.execute(
                        f"""
                        UPDATE {QUEUE_TABLE} SET CURRENT_LEVEL = :nlvl, PENDING_AT = :pa
                        WHERE QUEUE_ID = :qid
                        """,
                        {'nlvl': ncl, 'pa': pa[:120], 'qid': int(queue_id)},
                    )
                    conn.commit()
                    return True, f'Advanced to level {ncl} ({pa}).', False
                cur.execute(
                    f"""
                    UPDATE {QUEUE_TABLE} SET STATUS = 'APPROVED', ACTION_BY = :u, ACTION_AT = SYSDATE, REMARKS = :r
                    WHERE QUEUE_ID = :qid
                    """,
                    {'u': user[:100], 'r': (remarks or '')[:500], 'qid': int(queue_id)},
                )
                doc_no = rec.get('document_no') or ''
                tx = rec.get('transaction_type') or ''
            conn.commit()
        err = finalize_approved_document(tx, doc_no, loc_code)
        if err:
            return False, err, False
        return True, '', True
    except Exception as ex:
        return False, str(ex), False


def sync_lpo_submit(lpo_no: int, amount: float, user: str, loc_code: Optional[int] = None) -> None:
    loc = loc_code if loc_code is not None else _resolve_location_code()
    if not requires_approval(loc, 'LPO', amount):
        return
    enqueue_document(loc_code=loc, transaction_type='LPO', doc_no=lpo_no, amount=amount, created_by=user)


def sync_grn_submit(receipt_no: int, amount: float, user: str, loc_code: Optional[int] = None) -> None:
    loc = loc_code if loc_code is not None else _resolve_location_code()
    if not requires_approval(loc, 'GRN', amount):
        return
    enqueue_document(loc_code=loc, transaction_type='GRN', doc_no=receipt_no, amount=amount, created_by=user)


def evaluate_stock_adjustment_save(
    adj_no: Any,
    lines: List[Dict[str, Any]],
    user: str,
    adj_date: str,
    loc_code: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """Returns (needs_approval, error, queue_id)."""
    loc = loc_code if loc_code is not None else _resolve_location_code()
    pending = get_pending_queue_row(loc, 'STK_ADJ', adj_no)
    if pending:
        qid = int(pending.get('queue_id') or pending.get('QUEUE_ID') or 0)
        return True, None, qid or None
    if is_document_approved(loc, 'STK_ADJ', adj_no):
        rows = _safe_rows(
            f"""
            SELECT STATUS FROM {QUEUE_TABLE}
            WHERE LOCATIONCODE = :loc AND DOCUMENT_NO = :doc
            ORDER BY QUEUE_ID DESC
            """,
            {'loc': loc, 'doc': document_no_for('STK_ADJ', adj_no)},
        )
        if rows and str(rows[0].get('status') or rows[0].get('STATUS') or '').upper() == 'APPROVED':
            return False, None, None
    amount = 0.0
    for ln in lines or []:
        try:
            aq = abs(float(ln.get('adjust_qty') or 0))
            cost = float(ln.get('cost') or 0)
            amount += aq * cost if cost else aq
        except (TypeError, ValueError):
            pass
    if not requires_approval(loc, 'STK_ADJ', amount):
        return False, None, None
    ok, err, qid = enqueue_document(
        loc_code=loc,
        transaction_type='STK_ADJ',
        doc_no=adj_no,
        amount=amount,
        created_by=user,
        document_date=adj_date,
    )
    if not ok:
        return False, err, None
    return True, None, qid
