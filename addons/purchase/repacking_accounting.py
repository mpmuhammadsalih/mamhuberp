"""ITEMJOURNAL + GL posting for repacking (source out / output in)."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from db import (
    GL_DTL_SEQ,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    _get_connection,
    _journal_average_cost_for_line,
    ensure_gl_tables,
    ensure_itemjournal_averagecost_column,
    ensure_itemjournal_batch_columns,
    ensure_itemjournal_storage_id_column,
    ensure_itemjournal_surrogate_pk,
    ensure_itemjournal_warehouse_columns,
    get_all_chart_of_accounts,
    get_gl_voucher_detail,
    repost_itemjournal_repacking,
)

from addons.purchase.stock_adjustment_accounting import (
    _item_inventory_account_cur,
    _item_inventory_column_maps,
    _journal_lines_from_save_lines,
)


def _post_journal_enabled() -> bool:
    return os.getenv('REPACKING_POST_JOURNAL', os.getenv('STOCK_ADJUSTMENT_POST_JOURNAL', '1')).strip().lower() not in ('0', 'false', 'no')


def _post_gl_enabled() -> bool:
    return os.getenv('REPACKING_POST_GL', os.getenv('STOCK_ADJUSTMENT_POST_GL', '1')).strip().lower() not in ('0', 'false', 'no')


def repacking_gl_voucher_no(location_code: int, repack_no: int) -> str:
    return f'RP-{int(location_code)}-{int(repack_no)}'[:30]


def _build_repacking_gl_entry_rows(
    cur: Any,
    *,
    location_code: int,
    repack_no: int,
    journal_lines: List[Dict[str, Any]],
) -> tuple:
    """
    GL: Dr output item inventory, Cr source item inventory (per INVENTORYACCOUNT).
    Returns (rows, error) where rows are (account_code, debit, credit, remarks).
    """
    cols = _item_inventory_column_maps()
    item_cost_cache: Dict[int, float] = {}
    gl_rows: List[tuple] = []
    for row in journal_lines:
        try:
            ic = int(row.get('itemcode') or row.get('item_code') or 0)
            qty = float(row.get('base_qty') if row.get('base_qty') is not None else row.get('adjust_qty') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0 or abs(qty) < 1e-07:
            continue
        inv_acc = _item_inventory_account_cur(cur, int(location_code), ic, cols)
        avg_cost = _journal_average_cost_for_line(
            cur, int(location_code), row, item_cache=item_cost_cache,
        )
        amt = round(qty * avg_cost, 2)
        if abs(amt) < 0.005:
            continue
        if amt > 0:
            gl_rows.append((inv_acc, amt, 0.0, f'Repack #{repack_no} output inventory'))
        else:
            gl_rows.append((inv_acc, 0.0, abs(amt), f'Repack #{repack_no} source inventory'))

    tdr = round(sum(float(dr or 0) for _, dr, cr, _ in gl_rows), 2)
    tcr = round(sum(float(cr or 0) for _, dr, cr, _ in gl_rows), 2)
    diff = round(tdr - tcr, 2)
    if abs(diff) > 0.005:
        balance_acc = '1300'
        for row in journal_lines:
            try:
                qty = float(row.get('base_qty') if row.get('base_qty') is not None else row.get('adjust_qty') or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty < -1e-07:
                try:
                    ic = int(row.get('itemcode') or row.get('item_code') or 0)
                    balance_acc = _item_inventory_account_cur(cur, int(location_code), ic, cols)
                except (TypeError, ValueError):
                    pass
                break
        if diff > 0:
            gl_rows.append((balance_acc, 0.0, diff, f'Repack #{repack_no} cost balance'))
        else:
            gl_rows.append((balance_acc, abs(diff), 0.0, f'Repack #{repack_no} cost balance'))

    return (gl_rows, None)


def repacking_account_postings_for_pdf(
    location_code: int,
    repack_no: int,
    save_lines: List[Dict[str, Any]],
    *,
    gl_voucher_no: Optional[str] = None,
) -> Dict[str, Any]:
    """GL account lines for repacking PDF (posted voucher or computed preview)."""
    coa_names = {
        str(r.get('code') or '').strip(): str(r.get('name') or '').strip()
        for r in (get_all_chart_of_accounts() or [])
    }
    vno = (gl_voucher_no or '').strip() or repacking_gl_voucher_no(location_code, repack_no)

    detail = get_gl_voucher_detail(vno)
    if detail and detail.get('lines'):
        return {
            'voucher_no': str(detail.get('voucher_no') or vno),
            'is_posted': True,
            'is_preview': False,
            'lines': detail.get('lines') or [],
            'total_debit': float(detail.get('total_debit') or 0),
            'total_credit': float(detail.get('total_credit') or 0),
            'error': None,
        }

    journal_lines = _journal_lines_from_save_lines(save_lines)
    if not journal_lines:
        return {
            'voucher_no': vno,
            'is_posted': False,
            'is_preview': True,
            'lines': [],
            'total_debit': 0.0,
            'total_credit': 0.0,
            'error': None,
        }

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                gl_rows, err = _build_repacking_gl_entry_rows(
                    cur,
                    location_code=int(location_code),
                    repack_no=int(repack_no),
                    journal_lines=journal_lines,
                )
    except Exception as ex:
        gl_rows, err = [], str(ex)

    lines_out: List[Dict[str, Any]] = []
    tdr = tcr = 0.0
    for acc, dr, cr, rm in gl_rows or []:
        ac = str(acc or '').strip()
        dr_f = float(dr or 0)
        cr_f = float(cr or 0)
        tdr += dr_f
        tcr += cr_f
        lines_out.append({
            'account_code': ac,
            'account_name': coa_names.get(ac, '') or '—',
            'debit': round(dr_f, 2),
            'credit': round(cr_f, 2),
            'remarks': str(rm or ''),
        })

    return {
        'voucher_no': vno,
        'is_posted': False,
        'is_preview': True,
        'lines': lines_out,
        'total_debit': round(tdr, 2),
        'total_credit': round(tcr, 2),
        'error': err,
    }


def _post_repacking_gl_cur(
    cur: Any,
    *,
    location_code: int,
    repack_no: int,
    repack_date: str,
    journal_lines: List[Dict[str, Any]],
    posted_by: str,
) -> Optional[str]:
    """GL voucher: Dr output inventory / Cr source inventory."""
    if not ensure_gl_tables():
        return 'GL tables are not available.'
    gl_rows, err = _build_repacking_gl_entry_rows(
        cur,
        location_code=int(location_code),
        repack_no=int(repack_no),
        journal_lines=journal_lines,
    )
    if err:
        return err
    if not gl_rows:
        return None

    try:
        date_fmt = datetime.strptime(str(repack_date or '')[:10], '%Y-%m-%d').strftime('%d-%b-%Y').upper()
    except Exception:
        date_fmt = datetime.now().strftime('%d-%b-%Y').upper()

    gl_voucher_no = repacking_gl_voucher_no(location_code, repack_no)
    gl_ref_no = f'RP-{int(repack_no)}'[:50]
    gl_narration = f'Repacking #{repack_no}'[:500]
    gl_user = (posted_by or '')[:50]
    cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(
        f"""
        INSERT INTO {GL_HDR_TABLE}
            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
        VALUES
            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'REPACKING', :usr)
        """,
        {
            'vno': gl_voucher_no,
            'vdate': date_fmt,
            'ref': gl_ref_no,
            'nar': gl_narration,
            'usr': gl_user,
        },
    )
    gl_line_no = 1
    for acc, dr, cr, rm in gl_rows:
        cur.execute(f'SELECT {GL_DTL_SEQ}.NEXTVAL FROM DUAL')
        gl_line_id = cur.fetchone()[0]
        cur.execute(
            f"""
            INSERT INTO {GL_DTL_TABLE}
                (LINE_ID, VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS)
            VALUES
                (:lid, :vno, :ln, :acc, :dr, :cr, :rm)
            """,
            {
                'lid': gl_line_id,
                'vno': gl_voucher_no,
                'ln': gl_line_no,
                'acc': (acc or '1300')[:20],
                'dr': dr,
                'cr': cr,
                'rm': rm[:250],
            },
        )
        gl_line_no += 1
    return None


def post_repacking_accounting_cur(
    cur: Any,
    conn: Any,
    *,
    location_code: int,
    repack_no: int,
    repack_date: str,
    lines: List[Dict[str, Any]],
    posted_by: str,
    reset_no: int,
) -> Optional[str]:
    """ITEMJOURNAL + GL for a posted repacking document."""
    journal_lines = _journal_lines_from_save_lines(lines)
    if not journal_lines:
        return None

    if _post_journal_enabled():
        ensure_itemjournal_surrogate_pk(conn)
        ensure_itemjournal_storage_id_column()
        ensure_itemjournal_warehouse_columns()
        ensure_itemjournal_batch_columns()
        ensure_itemjournal_averagecost_column()
        for jl in journal_lines:
            for ln in lines or []:
                try:
                    if int(float(ln.get('item_code') or 0)) != int(jl.get('itemcode') or 0):
                        continue
                except (TypeError, ValueError):
                    continue
                if ln.get('from_storage_id') is not None:
                    jl['from_storage_id'] = ln.get('from_storage_id')
                if ln.get('to_storage_id') is not None:
                    jl['to_storage_id'] = ln.get('to_storage_id')
                if ln.get('lot_id') is not None:
                    jl['lot_id'] = ln.get('lot_id')
        try:
            repost_itemjournal_repacking(
                cur, conn, int(location_code), int(reset_no), int(repack_no), journal_lines,
            )
        except Exception as ex:
            return f'Item journal: {ex}'

    if _post_gl_enabled():
        gl_err = _post_repacking_gl_cur(
            cur,
            location_code=int(location_code),
            repack_no=int(repack_no),
            repack_date=repack_date,
            journal_lines=journal_lines,
            posted_by=posted_by,
        )
        if gl_err:
            return gl_err

    return None
