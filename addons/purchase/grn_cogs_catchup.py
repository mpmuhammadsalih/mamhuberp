"""BC-style COGS catch-up when a GRN covers prior negative (minus-billing) stock.

When stock was negative and sales already posted COGS at the old AVERAGECOST, a later
receipt brings the true unit cost. For the qty that fills the hole:

    covered = min(receipt_base_qty, max(0, -stock_before))
    adj     = covered × (receipt_landing − old_average_cost)

GL (same sense as BC Adjust Cost – Item Entries):
    adj > 0 → Dr COGS / Cr Inventory  (true cost higher than provisional)
    adj < 0 → Dr Inventory / Cr COGS
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    DEFAULT_PARTY_ACCOUNTS,
    GL_DTL_SEQ,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    ensure_gl_tables,
    get_item_by_code,
    resolve_item_inventory_gl_account,
)

_LOG = logging.getLogger('nexa.grn_cogs_catchup')


def compute_negative_stock_cogs_catchup(
    *,
    qty_on_hand: float,
    old_grn_qty: float,
    new_grn_qty: float,
    avg_on_hand: float,
    new_grn_landing: float,
    cost_on_hand: float = 0.0,
) -> Dict[str, float]:
    """
    Return covered qty and adjustment amount (0 when nothing to catch up).

    qty_on_hand is ITEMMASTER stock still including any old receipt qty of this GRN
    (same timing as _grn_compute_item_average_cost).

    Provisional unit cost must match sales COGS basis:
    NVL(AVERAGECOST, COSTPRICE) — not AVERAGECOST alone (often 0 while COSTPRICE was used).
    """
    q0 = float(qty_on_hand or 0)
    oq = max(0.0, float(old_grn_qty or 0))
    nq = max(0.0, float(new_grn_qty or 0))
    a0 = max(0.0, float(avg_on_hand or 0))
    c0 = max(0.0, float(cost_on_hand or 0))
    provisional = a0 if a0 > 1e-12 else c0
    nl = max(0.0, float(new_grn_landing or 0))
    # True stock before this receipt (may be negative — do not floor).
    stock_before = q0 - oq
    if nq <= 1e-12 or stock_before >= -1e-12:
        return {
            'stock_before': round(stock_before, 6),
            'covered_qty': 0.0,
            'unit_diff': 0.0,
            'adjustment': 0.0,
            'provisional_cost': round(provisional, 6),
        }
    hole = abs(stock_before)
    covered = min(nq, hole)
    unit_diff = round(nl - provisional, 6)
    adjustment = round(covered * unit_diff, 2)
    return {
        'stock_before': round(stock_before, 6),
        'covered_qty': round(covered, 6),
        'unit_diff': unit_diff,
        'adjustment': adjustment,
        'provisional_cost': round(provisional, 6),
    }


def _item_accounts(location_code: int, item_code: int) -> Tuple[str, str]:
    defaults = dict(DEFAULT_PARTY_ACCOUNTS or {})
    default_inv = str(defaults.get('inventory_asset') or '1300').strip()[:20]
    default_cogs = str(defaults.get('cogs') or '5100').strip()[:20]
    item = {}
    try:
        item = get_item_by_code(int(item_code), int(location_code)) or {}
    except Exception:
        item = {}
    inv = resolve_item_inventory_gl_account(
        item.get('inventory_account')
        or item.get('INVENTORY_ACCOUNT')
        or item.get('inventoryaccount'),
        default_inv,
    )
    cogs = str(
        item.get('cogs_account')
        or item.get('COGS_ACCOUNT')
        or item.get('cogsaccount')
        or default_cogs
    ).strip()[:20] or default_cogs
    return inv, cogs


def grn_cogs_catchup_voucher_no(location_code: int, receipt_no: Any) -> str:
    return f'GRN-CA-{int(location_code)}-{receipt_no}'[:40]


def post_grn_cogs_catchup_gl_cur(
    cur: Any,
    *,
    location_code: int,
    receipt_no: Any,
    voucher_date: Any,
    lines: List[Dict[str, Any]],
    posted_by: str = '',
) -> Optional[str]:
    """
    Post (or replace) one GL voucher for GRN minus-billing COGS catch-up.

    Each line: item_code, covered_qty, adjustment (signed: + means increase COGS).
    Returns voucher_no or None when nothing to post.
    """
    if not lines:
        return None
    if not ensure_gl_tables():
        _LOG.warning('GRN COGS catch-up skipped: GL tables unavailable')
        return None

    # Aggregate by (cogs_ac, inv_ac)
    buckets: Dict[Tuple[str, str], float] = {}
    remarks: Dict[Tuple[str, str], str] = {}
    for ln in lines:
        adj = round(float(ln.get('adjustment') or 0), 2)
        if abs(adj) < 0.005:
            continue
        ic = int(ln.get('item_code') or ln.get('itemcode') or 0)
        inv_ac = str(ln.get('inventory_account') or '').strip()[:20]
        cogs_ac = str(ln.get('cogs_account') or '').strip()[:20]
        if not inv_ac or not cogs_ac:
            resolved_inv, resolved_cogs = _item_accounts(location_code, ic)
            inv_ac = inv_ac or resolved_inv
            cogs_ac = cogs_ac or resolved_cogs
        key = (cogs_ac, inv_ac)
        buckets[key] = round(buckets.get(key, 0.0) + adj, 2)
        cov = float(ln.get('covered_qty') or 0)
        remarks[key] = (
            f"GRN COGS catch-up item {ic} qty {cov:g} "
            f"(minus billing → receipt {receipt_no})"
        )[:250]

    gl_rows: List[Tuple[str, float, float, str]] = []
    for (cogs_ac, inv_ac), adj in buckets.items():
        if abs(adj) < 0.005:
            continue
        amt = abs(adj)
        rm = remarks.get((cogs_ac, inv_ac), 'GRN COGS catch-up')[:250]
        if adj > 0:
            # True cost higher than provisional sale cost
            gl_rows.append((cogs_ac, amt, 0.0, rm))
            gl_rows.append((inv_ac, 0.0, amt, rm))
        else:
            gl_rows.append((inv_ac, amt, 0.0, rm))
            gl_rows.append((cogs_ac, 0.0, amt, rm))

    vno = grn_cogs_catchup_voucher_no(location_code, receipt_no)
    # Always clear prior voucher for this receipt (re-save / void catch-up).
    try:
        cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
        cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
    except Exception as ex:
        _LOG.warning('GRN COGS catch-up clear voucher %s: %s', vno, ex)

    if not gl_rows:
        return None

    if isinstance(voucher_date, datetime):
        d = voucher_date.date()
    elif isinstance(voucher_date, date):
        d = voucher_date
    else:
        try:
            d = datetime.strptime(str(voucher_date)[:10], '%Y-%m-%d').date()
        except Exception:
            d = date.today()
    date_fmt = d.strftime('%d-%b-%Y').upper()

    cur.execute(
        f"""
        INSERT INTO {GL_HDR_TABLE}
            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
        VALUES
            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'GRN_COGS_ADJ', :usr)
        """,
        {
            'vno': vno,
            'vdate': date_fmt,
            'ref': str(receipt_no)[:50],
            'nar': f'GRN COGS catch-up (minus billing) receipt {receipt_no}'[:500],
            'usr': (posted_by or '')[:50],
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
                'acc': (acc or '5100')[:20],
                'dr': round(float(dr), 2),
                'cr': round(float(cr), 2),
                'rm': (rm or '')[:250],
            },
        )
        line_no += 1
    _LOG.info(
        'GRN COGS catch-up posted voucher=%s receipt=%s lines=%s',
        vno,
        receipt_no,
        len(gl_rows) // 2,
    )
    return vno


def clear_grn_cogs_catchup_gl_cur(cur: Any, *, location_code: int, receipt_no: Any) -> None:
    """Remove catch-up voucher when GRN is deleted / unposted."""
    vno = grn_cogs_catchup_voucher_no(location_code, receipt_no)
    try:
        if not ensure_gl_tables():
            return
        cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
        cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': vno})
    except Exception as ex:
        _LOG.warning('clear GRN COGS catch-up %s: %s', vno, ex)
