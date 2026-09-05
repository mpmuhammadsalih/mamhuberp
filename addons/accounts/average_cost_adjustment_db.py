"""Average Cost Adjustment — update ITEMMASTER.AVERAGECOST with GL + COGS correction for minus billing."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    DEFAULT_PARTY_ACCOUNTS,
    GL_DTL_SEQ,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    _get_connection,
    _safe_rows,
    _table_exists,
    ensure_gl_tables,
    get_item_by_code,
    get_item_store_inventory,
    get_item_store_rows_from_itemmaster,
    get_warehouse_master_store_picker_rows,
    resolve_item_inventory_gl_account,
    resolve_stk_adj_variance_account_codes,
)

_LOG = logging.getLogger('nexa.average_cost_adjustment')

HDR_TABLE = 'AVGCOSTADJHDR'
DTL_TABLE = 'AVGCOSTADJDTL'

STATUS_DRAFT = 'DRAFT'
STATUS_IN_PROGRESS = 'IN_PROGRESS'
STATUS_POSTED = 'POSTED'

REASONS = (
    'Minus billing COGS correction',
    'Purchase cost catch-up',
    'Revaluation',
    'Price correction',
    'Other',
)


def ensure_average_cost_adjustment_tables() -> bool:
    if _table_exists(DTL_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'AVGCOSTADJHDR'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {HDR_TABLE} (
                            LOCATIONCODE      NUMBER(6) NOT NULL,
                            JOURNALNO         NUMBER(10) NOT NULL,
                            JOURNALNAME       VARCHAR2(50),
                            DESCRIPTION       VARCHAR2(500),
                            JOURNAL_DATE      DATE,
                            POSTING_DATE      DATE,
                            WAREHOUSE_CODE    VARCHAR2(30),
                            STATUS            VARCHAR2(20) DEFAULT 'DRAFT',
                            POSTED            CHAR(1) DEFAULT 'N',
                            NOTES             VARCHAR2(2000),
                            REFERENCE         VARCHAR2(100),
                            ADJUSTMENT_REASON VARCHAR2(100),
                            GL_VOUCHER_NO     VARCHAR2(40),
                            CREATEDBY         VARCHAR2(50),
                            CREATEDDATE       DATE,
                            POSTEDBY          VARCHAR2(50),
                            POSTEDDATE        DATE,
                            CONSTRAINT PK_AVGCOSTADJHDR PRIMARY KEY (LOCATIONCODE, JOURNALNO)
                        ) TABLESPACE USERS
                        """
                    )
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = 'AVGCOSTADJDTL'"
                )
                if int((cur.fetchone() or [0])[0] or 0) == 0:
                    cur.execute(
                        f"""
                        CREATE TABLE {DTL_TABLE} (
                            LOCATIONCODE       NUMBER(6) NOT NULL,
                            JOURNALNO          NUMBER(10) NOT NULL,
                            SLNO               NUMBER(4) NOT NULL,
                            ITEMCODE           NUMBER(12) NOT NULL,
                            ITEMNAME           VARCHAR2(250),
                            WAREHOUSE_CODE     VARCHAR2(30),
                            UNITOFMEASUREMENT  VARCHAR2(20),
                            CURRENT_QTY        NUMBER(14,3),
                            OLD_AVERAGE_COST   NUMBER(18,6),
                            NEW_AVERAGE_COST   NUMBER(18,6),
                            VALUE_DELTA        NUMBER(18,6),
                            CORRECTION_TYPE    VARCHAR2(30),
                            INVENTORY_ACCOUNT  VARCHAR2(20),
                            OFFSET_ACCOUNT     VARCHAR2(20),
                            LINEREMARKS        VARCHAR2(300),
                            CONSTRAINT PK_AVGCOSTADJDTL PRIMARY KEY (LOCATIONCODE, JOURNALNO, SLNO)
                        ) TABLESPACE USERS
                        """
                    )
            conn.commit()
        return True
    except Exception as ex:
        _LOG.error('ensure_average_cost_adjustment_tables: %s', ex)
        return False


def next_journal_no(location_code: int) -> int:
    ensure_average_cost_adjustment_tables()
    lc = int(location_code)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT NVL(MAX(JOURNALNO), 0) + 1 FROM {HDR_TABLE} WHERE LOCATIONCODE = :lc',
                {'lc': lc},
            )
            row = cur.fetchone()
            return int((row[0] if row else 1) or 1)


def format_journal_name(journal_no: int) -> str:
    try:
        n = int(journal_no)
    except (TypeError, ValueError):
        n = 0
    return f'ACA-{n:06d}'


def list_journals(
    location_code: int,
    *,
    search: str = '',
    status: str = '',
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_average_cost_adjustment_tables()
    lc = int(location_code)
    where = ['h.LOCATIONCODE = :lc']
    params: Dict[str, Any] = {'lc': lc, 'lim': max(20, min(int(limit or 200), 500))}
    if status:
        where.append('UPPER(TRIM(h.STATUS)) = :st')
        params['st'] = status.strip().upper()
    if search:
        where.append(
            "(TO_CHAR(h.JOURNALNO) LIKE :s OR UPPER(NVL(h.JOURNALNAME,'')) LIKE :su "
            "OR UPPER(NVL(h.DESCRIPTION,'')) LIKE :su OR UPPER(NVL(h.REFERENCE,'')) LIKE :su)"
        )
        params['s'] = f'%{search.strip()}%'
        params['su'] = f'%{search.strip().upper()}%'
    q = f"""
        SELECT * FROM (
            SELECT
                h.JOURNALNO AS journalno,
                h.JOURNALNAME AS journalname,
                h.DESCRIPTION AS description,
                h.JOURNAL_DATE AS journal_date,
                h.POSTING_DATE AS posting_date,
                h.WAREHOUSE_CODE AS warehouse_code,
                h.STATUS AS status,
                h.POSTED AS posted,
                h.REFERENCE AS reference,
                h.GL_VOUCHER_NO AS gl_voucher_no,
                h.CREATEDBY AS createdby,
                h.CREATEDDATE AS createddate,
                (SELECT NVL(SUM(d.VALUE_DELTA), 0) FROM {DTL_TABLE} d
                 WHERE d.LOCATIONCODE = h.LOCATIONCODE AND d.JOURNALNO = h.JOURNALNO) AS total_delta,
                (SELECT COUNT(*) FROM {DTL_TABLE} d
                 WHERE d.LOCATIONCODE = h.LOCATIONCODE AND d.JOURNALNO = h.JOURNALNO) AS line_count
            FROM {HDR_TABLE} h
            WHERE {' AND '.join(where)}
            ORDER BY h.JOURNALNO DESC
        ) WHERE ROWNUM <= :lim
    """
    rows = _safe_rows(q, params) or []
    for r in rows:
        if not r.get('journalname'):
            r['journalname'] = format_journal_name(r.get('journalno'))
    return rows


def get_journal_payload(location_code: int, journal_no: int) -> Optional[Dict[str, Any]]:
    ensure_average_cost_adjustment_tables()
    lc = int(location_code)
    jno = int(journal_no)
    hdr_rows = _safe_rows(
        f"""
        SELECT
            JOURNALNO AS journalno,
            JOURNALNAME AS journalname,
            DESCRIPTION AS description,
            JOURNAL_DATE AS journal_date,
            POSTING_DATE AS posting_date,
            WAREHOUSE_CODE AS warehouse_code,
            STATUS AS status,
            POSTED AS posted,
            NOTES AS notes,
            REFERENCE AS reference,
            ADJUSTMENT_REASON AS adjustment_reason,
            GL_VOUCHER_NO AS gl_voucher_no,
            CREATEDBY AS createdby,
            CREATEDDATE AS createddate,
            POSTEDBY AS postedby,
            POSTEDDATE AS posteddate
        FROM {HDR_TABLE}
        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
        """,
        {'lc': lc, 'jno': jno},
    ) or []
    if not hdr_rows:
        return None
    lines = _safe_rows(
        f"""
        SELECT
            SLNO AS slno,
            ITEMCODE AS itemcode,
            ITEMNAME AS itemname,
            WAREHOUSE_CODE AS warehouse_code,
            UNITOFMEASUREMENT AS uom,
            CURRENT_QTY AS current_qty,
            OLD_AVERAGE_COST AS old_average_cost,
            NEW_AVERAGE_COST AS new_average_cost,
            VALUE_DELTA AS value_delta,
            CORRECTION_TYPE AS correction_type,
            INVENTORY_ACCOUNT AS inventory_account,
            OFFSET_ACCOUNT AS offset_account,
            LINEREMARKS AS lineremarks
        FROM {DTL_TABLE}
        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
        ORDER BY SLNO
        """,
        {'lc': lc, 'jno': jno},
    ) or []
    hdr = hdr_rows[0]
    if not hdr.get('journalname'):
        hdr['journalname'] = format_journal_name(jno)
    return {'header': hdr, 'lines': lines}


def list_warehouse_options(location_code: int) -> List[Dict[str, Any]]:
    try:
        rows = get_warehouse_master_store_picker_rows(int(location_code)) or []
        out = []
        for r in rows:
            out.append({
                'id': r.get('warehouse_id') or r.get('id'),
                'code': r.get('store') or r.get('warehouse_code') or r.get('code'),
                'name': r.get('name') or r.get('warehouse_name') or '',
            })
        return out
    except Exception as ex:
        _LOG.warning('list_warehouse_options: %s', ex)
        return []


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _item_accounts(item: Dict[str, Any]) -> Tuple[str, str]:
    defaults = dict(DEFAULT_PARTY_ACCOUNTS or {})
    default_inv = str(defaults.get('inventory_asset') or '1300').strip()[:20]
    default_cogs = str(defaults.get('cogs') or '5100').strip()[:20]
    inv = resolve_item_inventory_gl_account(
        item.get('inventory_account') or item.get('INVENTORY_ACCOUNT') or item.get('inventoryaccount'),
        default_inv,
    )
    cogs = str(
        item.get('cogs_account')
        or item.get('COGS_ACCOUNT')
        or item.get('cogsaccount')
        or default_cogs
    ).strip()[:20] or default_cogs
    return inv, cogs


def _variance_account(delta: float) -> str:
    codes = resolve_stk_adj_variance_account_codes()
    if delta >= 0:
        return str(codes.get('increase') or DEFAULT_PARTY_ACCOUNTS.get('inventory_adjustment') or '5199')[:20]
    return str(codes.get('decrease') or DEFAULT_PARTY_ACCOUNTS.get('inventory_adjustment') or '5199')[:20]


def compute_line_preview(
    location_code: int,
    item_code: int,
    new_average_cost: float,
    warehouse_code: str = '',
) -> Dict[str, Any]:
    """Compute qty, old/new avg, value delta and correction type for one item."""
    snap = _item_inventory_snapshot(location_code, item_code, warehouse_code)
    old_avg = float(snap['current_avg_cost'] or 0)
    qty = float(snap['current_qty'] or 0)
    new_avg = float(new_average_cost or 0)
    delta = round(qty * (new_avg - old_avg), 2)
    if abs(qty) < 1e-9:
        corr = 'COST_ONLY'
    elif qty < 0:
        corr = 'COGS_CORRECTION'
    else:
        corr = 'REVALUATION'
    inv_ac, cogs_ac = _item_accounts(snap.get('_item') or {})
    if corr == 'COGS_CORRECTION':
        offset = cogs_ac
    elif corr == 'COST_ONLY':
        offset = ''
    else:
        offset = _variance_account(delta)
    return {
        'success': True,
        'itemcode': snap['itemcode'],
        'itemname': snap['itemname'],
        'uom': snap['uom'],
        'current_qty': qty,
        'old_average_cost': old_avg,
        'new_average_cost': new_avg,
        'value_delta': delta,
        'correction_type': corr,
        'inventory_account': inv_ac,
        'offset_account': offset,
        'warehouse_code': snap.get('warehouse_code') or '',
    }


def _item_inventory_snapshot(
    location_code: int,
    item_code: int,
    warehouse_code: str = '',
) -> Dict[str, Any]:
    ic = int(item_code)
    loc = int(location_code)
    wh = (warehouse_code or '').strip().upper()
    item = get_item_by_code(ic, loc) or {}
    rows = get_item_store_inventory(loc, ic) or []
    if not rows:
        try:
            rows = get_item_store_rows_from_itemmaster(ic, loc) or []
        except Exception:
            rows = []
    current_qty = 0.0
    if wh:
        for r in rows:
            rs = str(r.get('store') or r.get('itemlocation') or '').strip().upper()
            if rs == wh:
                current_qty = float(r.get('stock') or 0)
                break
    elif rows:
        current_qty = sum(float(r.get('stock') or 0) for r in rows)
    else:
        try:
            current_qty = float(item.get('currentstock') or item.get('CURRENTSTOCK') or 0)
        except (TypeError, ValueError):
            current_qty = 0.0
    avg_cost = float(
        item.get('averagecost')
        or item.get('AVERAGECOST')
        or item.get('cost')
        or item.get('costprice')
        or item.get('COSTPRICE')
        or 0
    )
    return {
        'itemcode': ic,
        'itemname': item.get('name') or item.get('ITEMNAME') or item.get('itemname') or '',
        'uom': item.get('uom') or item.get('BASEUOM') or item.get('baseuom') or '',
        'current_qty': current_qty,
        'current_avg_cost': avg_cost,
        'current_inv_value': round(current_qty * avg_cost, 2),
        'warehouse_code': wh,
        '_item': item,
    }


def get_item_line_context(
    location_code: int,
    item_code: int,
    warehouse_code: str = '',
) -> Dict[str, Any]:
    snap = _item_inventory_snapshot(location_code, item_code, warehouse_code)
    inv_ac, cogs_ac = _item_accounts(snap.get('_item') or {})
    qty = float(snap['current_qty'] or 0)
    if abs(qty) < 1e-9:
        corr = 'COST_ONLY'
    elif qty < 0:
        corr = 'COGS_CORRECTION'
    else:
        corr = 'REVALUATION'
    return {
        'success': True,
        'itemcode': snap['itemcode'],
        'itemname': snap['itemname'],
        'uom': snap['uom'],
        'current_qty': qty,
        'old_average_cost': snap['current_avg_cost'],
        'current_avg_cost': snap['current_avg_cost'],
        'current_inv_value': snap['current_inv_value'],
        'correction_type': corr,
        'inventory_account': inv_ac,
        'cogs_account': cogs_ac,
        'warehouse_code': snap.get('warehouse_code') or '',
    }


def list_negative_stock_candidates(
    location_code: int,
    *,
    warehouse_code: str = '',
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Items with negative on-hand qty (minus billing candidates)."""
    ensure_average_cost_adjustment_tables()
    lc = int(location_code)
    lim = max(10, min(int(limit or 100), 300))
    wh = (warehouse_code or '').strip().upper()
    out: List[Dict[str, Any]] = []
    # Prefer STOREINVENTORY / item store rows via ITEMMASTER CURRENTSTOCK < 0
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT
                im.ITEMCODE AS itemcode,
                im.ITEMNAME AS itemname,
                im.BASEUOM AS uom,
                NVL(im.AVERAGECOST, NVL(im.COSTPRICE, 0)) AS averagecost,
                NVL(im.CURRENTSTOCK, 0) AS currentstock
            FROM ITEMMASTER im
            WHERE im.LOCATIONCODE = :lc
              AND NVL(im.CURRENTSTOCK, 0) < 0
            ORDER BY im.CURRENTSTOCK ASC, im.ITEMCODE
        ) WHERE ROWNUM <= :lim
        """,
        {'lc': lc, 'lim': lim},
    ) or []
    for r in rows:
        try:
            ic = int(r.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0:
            continue
        ctx = get_item_line_context(lc, ic, wh)
        if float(ctx.get('current_qty') or 0) >= 0 and not wh:
            # CURRENTSTOCK negative but store sum not — still include master negative
            ctx['current_qty'] = float(r.get('currentstock') or 0)
            ctx['correction_type'] = 'COGS_CORRECTION'
        if float(ctx.get('current_qty') or 0) >= 0:
            continue
        out.append({
            'itemcode': ctx['itemcode'],
            'itemname': ctx.get('itemname') or r.get('itemname') or '',
            'uom': ctx.get('uom') or r.get('uom') or '',
            'current_qty': ctx['current_qty'],
            'old_average_cost': ctx.get('old_average_cost') or float(r.get('averagecost') or 0),
            'correction_type': 'COGS_CORRECTION',
            'inventory_account': ctx.get('inventory_account'),
            'cogs_account': ctx.get('cogs_account'),
        })
        if len(out) >= lim:
            break
    return out


def search_items(
    location_code: int,
    *,
    search: str = '',
    warehouse_code: str = '',
    limit: int = 50,
) -> List[Dict[str, Any]]:
    lc = int(location_code)
    lim = max(10, min(int(limit or 50), 200))
    s = (search or '').strip()
    params: Dict[str, Any] = {'lc': lc, 'lim': lim}
    where = ['im.LOCATIONCODE = :lc']
    if s:
        if s.isdigit():
            where.append('(im.ITEMCODE = :ic OR UPPER(NVL(im.ITEMNAME,\'\')) LIKE :su OR UPPER(NVL(im.MANUFACTURERID,\'\')) LIKE :su)')
            params['ic'] = int(s)
            params['su'] = f'%{s.upper()}%'
        else:
            where.append('(UPPER(NVL(im.ITEMNAME,\'\')) LIKE :su OR UPPER(NVL(im.MANUFACTURERID,\'\')) LIKE :su OR TO_CHAR(im.ITEMCODE) LIKE :s)')
            params['su'] = f'%{s.upper()}%'
            params['s'] = f'%{s}%'
    q = f"""
        SELECT * FROM (
            SELECT
                im.ITEMCODE AS itemcode,
                im.ITEMNAME AS itemname,
                im.BASEUOM AS uom,
                NVL(im.AVERAGECOST, NVL(im.COSTPRICE, 0)) AS averagecost,
                NVL(im.CURRENTSTOCK, 0) AS currentstock
            FROM ITEMMASTER im
            WHERE {' AND '.join(where)}
            ORDER BY im.ITEMCODE
        ) WHERE ROWNUM <= :lim
    """
    rows = _safe_rows(q, params) or []
    out: List[Dict[str, Any]] = []
    wh = (warehouse_code or '').strip()
    for r in rows:
        try:
            ic = int(r.get('itemcode') or 0)
        except (TypeError, ValueError):
            continue
        ctx = get_item_line_context(lc, ic, wh) if ic else {}
        out.append({
            'code': ic,
            'name': ctx.get('itemname') or r.get('itemname') or '',
            'uom': ctx.get('uom') or r.get('uom') or '',
            'averagecost': ctx.get('old_average_cost') if ctx else float(r.get('averagecost') or 0),
            'stock': ctx.get('current_qty') if ctx else float(r.get('currentstock') or 0),
            'correction_type': ctx.get('correction_type') or 'REVALUATION',
        })
    return out


def _gl_voucher_no(location_code: int, journal_no: int) -> str:
    return f'ACA-{int(location_code)}-{int(journal_no)}'[:40]


def _post_gl_cur(
    cur,
    *,
    location_code: int,
    journal_no: int,
    journal_date: date,
    lines: List[Dict[str, Any]],
    user: str,
) -> Optional[str]:
    """Post one balanced GL voucher for all lines with non-zero value delta. Returns voucher no or None."""
    if not ensure_gl_tables():
        return None
    # Aggregate by (inv_ac, offset_ac) signed amounts
    buckets: Dict[Tuple[str, str], float] = {}
    remarks: Dict[Tuple[str, str], str] = {}
    for ln in lines:
        delta = round(float(ln.get('value_delta') or 0), 2)
        if abs(delta) < 0.005:
            continue
        corr = str(ln.get('correction_type') or '').upper()
        if corr == 'COST_ONLY':
            continue
        inv = str(ln.get('inventory_account') or '1300').strip()[:20] or '1300'
        off = str(ln.get('offset_account') or '').strip()[:20]
        if not off:
            continue
        key = (inv, off)
        buckets[key] = round(buckets.get(key, 0.0) + delta, 2)
        tag = 'COGS corr' if corr == 'COGS_CORRECTION' else 'Reval'
        remarks[key] = f"{tag} item {ln.get('itemcode')}"[:250]

    gl_rows: List[Tuple[str, float, float, str]] = []
    for (inv, off), delta in buckets.items():
        if abs(delta) < 0.005:
            continue
        amt = abs(delta)
        rm = remarks.get((inv, off), 'Average cost adjustment')[:250]
        if delta > 0:
            # Inventory value up: Dr Inventory / Cr offset
            gl_rows.append((inv, amt, 0.0, rm))
            gl_rows.append((off, 0.0, amt, rm))
        else:
            # Inventory value down: Dr offset / Cr Inventory
            gl_rows.append((off, amt, 0.0, rm))
            gl_rows.append((inv, 0.0, amt, rm))

    if not gl_rows:
        return None

    vno = _gl_voucher_no(location_code, journal_no)
    try:
        date_fmt = journal_date.strftime('%d-%b-%Y').upper()
    except Exception:
        date_fmt = datetime.now().strftime('%d-%b-%Y').upper()

    cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
    cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
    cur.execute(
        f"""
        INSERT INTO {GL_HDR_TABLE}
            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
        VALUES
            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'AVG_COST_ADJ', :usr)
        """,
        {
            'vno': vno,
            'vdate': date_fmt,
            'ref': format_journal_name(journal_no)[:50],
            'nar': f'Average cost adjustment #{format_journal_name(journal_no)}'[:500],
            'usr': (user or '')[:50],
        },
    )
    line_no = 1
    for acc, dr, cr, rm in gl_rows:
        cur.execute(f'SELECT {GL_DTL_SEQ}.NEXTVAL FROM DUAL')
        lid = cur.fetchone()[0]
        cur.execute(
            f"""
            INSERT INTO {GL_DTL_TABLE}
                (LINE_ID, VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS)
            VALUES
                (:lid, :vno, :ln, :acc, :dr, :cr, :rm)
            """,
            {
                'lid': lid,
                'vno': vno,
                'ln': line_no,
                'acc': (acc or '1300')[:20],
                'dr': round(float(dr), 2),
                'cr': round(float(cr), 2),
                'rm': (rm or '')[:250],
            },
        )
        line_no += 1
    return vno


def save_journal(
    location_code: int,
    *,
    journal_no: Optional[int],
    user: str,
    header: Dict[str, Any],
    lines: List[Dict[str, Any]],
    post: bool = False,
) -> Tuple[bool, str, Optional[int]]:
    ensure_average_cost_adjustment_tables()
    lc = int(location_code)
    if not lines:
        return (False, 'Add at least one line.', None)
    jno = int(journal_no) if journal_no else next_journal_no(lc)
    jname = (header.get('journalname') or '').strip() or format_journal_name(jno)
    desc = (header.get('description') or '').strip()[:500]
    journal_date = _parse_date(header.get('journal_date')) or date.today()
    posting_date = _parse_date(header.get('posting_date')) or journal_date
    wh_code = (header.get('warehouse_code') or '').strip()[:30]
    notes = (header.get('notes') or '').strip()[:2000]
    reference = (header.get('reference') or '').strip()[:100]
    adj_reason = (header.get('adjustment_reason') or '').strip()[:100]
    status = STATUS_POSTED if post else STATUS_IN_PROGRESS
    posted_flag = 'Y' if post else 'N'

    existing = get_journal_payload(lc, jno)
    if existing and str(existing['header'].get('posted') or 'N').upper() == 'Y':
        return (False, 'Posted journals cannot be changed.', jno)

    norm_lines: List[Dict[str, Any]] = []
    for i, ln in enumerate(lines, start=1):
        try:
            ic = int(ln.get('itemcode') or ln.get('item_code') or 0)
        except (TypeError, ValueError):
            return (False, f'Line {i}: invalid item code.', jno)
        if ic <= 0:
            return (False, f'Line {i}: item is required.', jno)
        try:
            new_avg = float(ln.get('new_average_cost') or 0)
        except (TypeError, ValueError):
            return (False, f'Line {i}: invalid new average cost.', jno)
        if new_avg < 0:
            return (False, f'Line {i}: new average cost cannot be negative.', jno)
        preview = compute_line_preview(
            lc, ic, new_avg, (ln.get('warehouse_code') or wh_code or '').strip()
        )
        # Allow draft save with zero delta (cost-only or same cost); on post still update AVERAGECOST
        norm_lines.append({
            'slno': int(ln.get('slno') or i),
            'itemcode': ic,
            'itemname': (ln.get('itemname') or preview.get('itemname') or '')[:250],
            'warehouse_code': (ln.get('warehouse_code') or wh_code or preview.get('warehouse_code') or '')[:30],
            'uom': (ln.get('uom') or preview.get('uom') or '')[:20],
            'current_qty': float(preview.get('current_qty') or 0),
            'old_average_cost': float(preview.get('old_average_cost') or 0),
            'new_average_cost': new_avg,
            'value_delta': float(preview.get('value_delta') or 0),
            'correction_type': (preview.get('correction_type') or 'REVALUATION')[:30],
            'inventory_account': (preview.get('inventory_account') or '1300')[:20],
            'offset_account': (preview.get('offset_account') or '')[:20],
            'lineremarks': (ln.get('lineremarks') or '')[:300],
        })

    if post:
        for ln in norm_lines:
            if float(ln['new_average_cost'] or 0) < 0:
                return (False, f"Item {ln['itemcode']}: new average cost invalid.", jno)

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if existing:
                    cur.execute(
                        f'DELETE FROM {DTL_TABLE} WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno',
                        {'lc': lc, 'jno': jno},
                    )
                    cur.execute(
                        f"""
                        UPDATE {HDR_TABLE} SET
                            JOURNALNAME = :jname,
                            DESCRIPTION = :desc,
                            JOURNAL_DATE = :jdate,
                            POSTING_DATE = :pdate,
                            WAREHOUSE_CODE = :wh_code,
                            STATUS = :status,
                            POSTED = :posted,
                            NOTES = :notes,
                            REFERENCE = :ref,
                            ADJUSTMENT_REASON = :reason
                        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
                        """,
                        {
                            'jname': jname, 'desc': desc,
                            'jdate': journal_date, 'pdate': posting_date,
                            'wh_code': wh_code, 'status': status, 'posted': posted_flag,
                            'notes': notes, 'ref': reference, 'reason': adj_reason,
                            'lc': lc, 'jno': jno,
                        },
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {HDR_TABLE} (
                            LOCATIONCODE, JOURNALNO, JOURNALNAME, DESCRIPTION,
                            JOURNAL_DATE, POSTING_DATE, WAREHOUSE_CODE, STATUS, POSTED,
                            NOTES, REFERENCE, ADJUSTMENT_REASON,
                            CREATEDBY, CREATEDDATE
                        ) VALUES (
                            :lc, :jno, :jname, :desc,
                            :jdate, :pdate, :wh_code, :status, :posted,
                            :notes, :ref, :reason,
                            :user, SYSDATE
                        )
                        """,
                        {
                            'lc': lc, 'jno': jno, 'jname': jname, 'desc': desc,
                            'jdate': journal_date, 'pdate': posting_date,
                            'wh_code': wh_code, 'status': status, 'posted': posted_flag,
                            'notes': notes, 'ref': reference, 'reason': adj_reason,
                            'user': (user or 'web')[:50],
                        },
                    )
                for ln in norm_lines:
                    cur.execute(
                        f"""
                        INSERT INTO {DTL_TABLE} (
                            LOCATIONCODE, JOURNALNO, SLNO, ITEMCODE, ITEMNAME,
                            WAREHOUSE_CODE, UNITOFMEASUREMENT,
                            CURRENT_QTY, OLD_AVERAGE_COST, NEW_AVERAGE_COST, VALUE_DELTA,
                            CORRECTION_TYPE, INVENTORY_ACCOUNT, OFFSET_ACCOUNT, LINEREMARKS
                        ) VALUES (
                            :lc, :jno, :sl, :ic, :iname,
                            :wh_code, :uom,
                            :cq, :old_avg, :new_avg, :delta,
                            :corr, :inv_ac, :off_ac, :rmk
                        )
                        """,
                        {
                            'lc': lc, 'jno': jno, 'sl': ln['slno'], 'ic': ln['itemcode'],
                            'iname': ln['itemname'], 'wh_code': ln['warehouse_code'],
                            'uom': ln['uom'], 'cq': ln['current_qty'],
                            'old_avg': ln['old_average_cost'], 'new_avg': ln['new_average_cost'],
                            'delta': ln['value_delta'], 'corr': ln['correction_type'],
                            'inv_ac': ln['inventory_account'], 'off_ac': ln['offset_account'],
                            'rmk': ln['lineremarks'],
                        },
                    )
                gl_vno = None
                if post:
                    for ln in norm_lines:
                        new_avg = float(ln['new_average_cost'] or 0)
                        if new_avg < 0:
                            continue
                        cur.execute(
                            """
                            SELECT COUNT(*) FROM user_tab_columns
                            WHERE table_name = 'ITEMMASTER' AND column_name = 'AVERAGECOST'
                            """
                        )
                        if int((cur.fetchone() or [0])[0] or 0) == 0:
                            continue
                        cur.execute(
                            """
                            UPDATE ITEMMASTER
                            SET AVERAGECOST = :avg
                            WHERE ITEMCODE = :ic AND LOCATIONCODE = :lc
                            """,
                            {'avg': new_avg, 'ic': int(ln['itemcode']), 'lc': lc},
                        )
                        # Fallback if location-scoped update hits 0 rows
                        if cur.rowcount == 0:
                            cur.execute(
                                """
                                UPDATE ITEMMASTER
                                SET AVERAGECOST = :avg
                                WHERE ITEMCODE = :ic
                                """,
                                {'avg': new_avg, 'ic': int(ln['itemcode'])},
                            )
                    gl_vno = _post_gl_cur(
                        cur,
                        location_code=lc,
                        journal_no=jno,
                        journal_date=posting_date,
                        lines=norm_lines,
                        user=user,
                    )
                    cur.execute(
                        f"""
                        UPDATE {HDR_TABLE}
                        SET STATUS = :st, POSTED = 'Y', POSTEDBY = :user, POSTEDDATE = SYSDATE,
                            GL_VOUCHER_NO = :gv
                        WHERE LOCATIONCODE = :lc AND JOURNALNO = :jno
                        """,
                        {
                            'st': STATUS_POSTED,
                            'user': (user or 'web')[:50],
                            'gv': (gl_vno or '')[:40] or None,
                            'lc': lc,
                            'jno': jno,
                        },
                    )
            conn.commit()
        msg = 'Posted successfully.' if post else 'Saved successfully.'
        if post and gl_vno:
            msg = f'Posted successfully. GL voucher {gl_vno}.'
        elif post:
            msg = 'Posted successfully. Average cost updated (no GL — zero stock or zero delta).'
        return (True, msg, jno)
    except Exception as ex:
        _LOG.exception('save_journal failed')
        return (False, str(ex), jno)
