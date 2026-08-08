"""Post stock adjustment inventory + accounting after workflow approval (status W → P)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from db import _detect_column, _detect_table, _get_connection


def post_stock_adjustment_after_approval(adj_no: Any, location_code: int) -> Optional[str]:
    """Apply inventory and ITEMJOURNAL/GL postings for a saved adjustment awaiting approval."""
    from addons.purchase.controllers.routes import (
        RESET_NO,
        ADJNO_SPEC,
        _ensure_stock_adjustment_tables,
        _get_stock_adjustment_payload,
        _grn_normalize_uom_key,
        _repair_stock_adjustment_schema,
        _run_inventory_postings_after_lines,
        adjno_match_params,
        adjno_match_sql,
        coerce_adjno,
    )
    from addons.purchase.stock_adjustment_accounting import post_stock_adjustment_accounting_cur
    from flask import session

    bind_no = coerce_adjno(adj_no)
    adj_ref = ADJNO_SPEC.numeric_ref(bind_no)
    payload = _get_stock_adjustment_payload(bind_no)
    if not payload:
        return 'Stock adjustment not found.'
    header = payload.get('header') or {}
    adj_date = str(header.get('adj_date') or '')[:10]
    opening_stock = bool(header.get('opening_stock'))
    lines: List[Dict[str, Any]] = []
    for ln in payload.get('lines') or []:
        lines.append({
            'item_code': ln.get('item_code'),
            'item_name': ln.get('item_name'),
            'uom': ln.get('uom'),
            'store': ln.get('store'),
            'current_qty': ln.get('current_qty'),
            'adjust_qty': ln.get('adjust_qty'),
            'new_qty': ln.get('new_qty'),
            'base_qty': ln.get('base_qty'),
            'cost': ln.get('cost'),
        })
    if not lines:
        return 'No adjustment lines.'
    hdr = _detect_table(['STKADJHDR', 'stockadjustmenthdr'])
    h_no = _detect_column(hdr, ['ADJNO', 'ADJUSTNO', 'DOCNO']) or 'ADJNO'
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    h_reset = _detect_column(hdr, ['RESETNO', 'resetno'])
    h_status = _detect_column(hdr, ['STATUS', 'status'])
    loc_code = int(location_code)
    new_map: Dict[tuple, float] = defaultdict(float)
    old_item_uom_qty: Dict[tuple, float] = defaultdict(float)
    lot_line_ops: List[Tuple[float, int, Optional[int], int, float]] = []
    for idx, ln in enumerate(lines, start=1):
        item_int = int(float(ln.get('item_code') or 0))
        if item_int <= 0:
            continue
        uom = str(ln.get('uom') or 'NOS').strip()
        store = str(ln.get('store') or '').strip().upper()
        base_qty = float(ln.get('base_qty') or ln.get('adjust_qty') or 0)
        cost = float(ln.get('cost') or 0)
        new_map[(item_int, store)] += base_qty
        old_item_uom_qty[(item_int, _grn_normalize_uom_key(uom))] += float(ln.get('adjust_qty') or 0)
        lot_line_ops.append((base_qty, item_int, None, idx, cost))
    with _get_connection() as conn:
        try:
            try:
                conn.autocommit = False
            except Exception:
                pass
            with conn.cursor() as cur:
                _repair_stock_adjustment_schema(cur)
                perr = _run_inventory_postings_after_lines(
                    conn, cur, lines, int(adj_ref), loc_code, {}, new_map, lot_line_ops,
                    lot_ref_type='STKADJ', batch_prefix='ADJ',
                    old_item_uom_qty=dict(old_item_uom_qty),
                )
                if perr:
                    raise ValueError(perr)
                aerr = post_stock_adjustment_accounting_cur(
                    cur,
                    conn,
                    location_code=loc_code,
                    adj_no=bind_no,
                    adj_date=adj_date,
                    lines=lines,
                    posted_by=str(session.get('user') or 'web'),
                    reset_no=int(RESET_NO),
                    opening_stock=opening_stock,
                )
                if aerr:
                    raise ValueError(aerr)
                if h_status:
                    wh = [adjno_match_sql(h_no, bind_prefix='adj')]
                    prm: Dict[str, Any] = dict(adjno_match_params(bind_no, bind_prefix='adj'))
                    prm['st'] = 'P'
                    if h_loc:
                        wh.append(f'{h_loc} = :loc')
                        prm['loc'] = loc_code
                    if h_reset:
                        wh.append(f'{h_reset} = :rn')
                        prm['rn'] = RESET_NO
                    cur.execute(f"UPDATE {hdr} SET {h_status} = :st WHERE {' AND '.join(wh)}", prm)
            conn.commit()
        except ValueError as ve:
            try:
                conn.rollback()
            except Exception:
                pass
            return str(ve)
        except Exception as ex:
            try:
                conn.rollback()
            except Exception:
                pass
            return str(ex)
    return None
