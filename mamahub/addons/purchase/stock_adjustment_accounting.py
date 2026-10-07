"""ITEMJOURNAL + GL posting for stock adjustments (Option C — mirrors stock count accounting)."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from db import (
    GL_DTL_SEQ,
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    _detect_column,
    _detect_table,
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
    repost_itemjournal_stock_adjustment,
    resolve_item_inventory_gl_account,
    resolve_stk_adj_variance_account_codes,
    _batch_itemmaster_journal_cost_map,
    _norm_gl_account_code,
)
from db.inventory_doc_numbers import ADJNO_SPEC, coerce_adjno


def _stk_adj_no_numeric_ref(adj_no: Any) -> int:
    try:
        return max(0, int(ADJNO_SPEC.numeric_ref(adj_no) or 0))
    except (TypeError, ValueError):
        return 0


def _stk_adj_no_label(adj_no: Any) -> str:
    s = str(coerce_adjno(adj_no) or adj_no or '').strip()
    if s:
        return s
    n = _stk_adj_no_numeric_ref(adj_no)
    return str(n) if n > 0 else ''


def _post_journal_enabled() -> bool:
    return os.getenv('STOCK_ADJUSTMENT_POST_JOURNAL', '1').strip().lower() not in ('0', 'false', 'no')


def _post_gl_enabled() -> bool:
    return os.getenv('STOCK_ADJUSTMENT_POST_GL', '1').strip().lower() not in ('0', 'false', 'no')


def stock_adjustment_gl_voucher_no(location_code: int, adj_no: Any) -> str:
    n = _stk_adj_no_numeric_ref(adj_no)
    if n > 0:
        return f'SA-{int(location_code)}-{n}'[:30]
    label = _stk_adj_no_label(adj_no)
    return label[:30] if label else f'SA-{int(location_code)}-0'[:30]


def _item_inventory_column_maps() -> Dict[str, Any]:
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    return {
        'im_tbl': im_tbl,
        'im_code': _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im_tbl else None,
        'im_loc': _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im_tbl else None,
    }


def _item_inventory_account_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    cols: Dict[str, Any],
) -> str:
    im_tbl = cols.get('im_tbl')
    im_code = cols.get('im_code')
    im_loc = cols.get('im_loc')
    im_inv = _detect_column(im_tbl, ['INVENTORYACCOUNT', 'INVENTORY_ACCOUNT', 'inventoryaccount']) if im_tbl else None
    if not im_tbl or not im_code or not im_inv:
        return '1300'
    where_parts = [f'{im_code} = :icode']
    params: Dict[str, Any] = {'icode': int(item_code)}
    if im_loc:
        where_parts.append(f'{im_loc} = :loc')
        params['loc'] = int(location_code)
    try:
        cur.execute(
            f"SELECT TRIM(TO_CHAR(NVL(NULLIF({im_inv}, 0), 1300))) FROM {im_tbl} WHERE {' AND '.join(where_parts)}",
            params,
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return resolve_item_inventory_gl_account(row[0])
    except Exception:
        pass
    return '1300'


def _batch_item_inventory_accounts_cur(
    cur: Any,
    location_code: int,
    item_codes: List[int],
    cols: Dict[str, Any],
) -> Dict[int, str]:
    """Batch-resolve INVENTORYACCOUNT for many items (chunked IN query)."""
    out: Dict[int, str] = {}
    uniq = sorted({int(c) for c in item_codes if c and int(c) > 0})
    if not uniq:
        return out
    im_tbl = cols.get('im_tbl')
    im_code = cols.get('im_code')
    im_loc = cols.get('im_loc')
    im_inv = _detect_column(im_tbl, ['INVENTORYACCOUNT', 'INVENTORY_ACCOUNT', 'inventoryaccount']) if im_tbl else None
    if not im_tbl or not im_code or not im_inv:
        for ic in uniq:
            out[ic] = '1300'
        return out
    chunk_size = 400
    for ci in range(0, len(uniq), chunk_size):
        chunk = uniq[ci:ci + chunk_size]
        keys = [f'ic_{ci}_{i}' for i in range(len(chunk))]
        binds = ','.join(f':{k}' for k in keys)
        params: Dict[str, Any] = {k: int(v) for k, v in zip(keys, chunk)}
        where = [f'{im_code} IN ({binds})']
        if im_loc:
            where.append(f'{im_loc} = :loc')
            params['loc'] = int(location_code)
        try:
            cur.execute(
                f'SELECT {im_code} AS itemcode, TRIM(TO_CHAR(NVL(NULLIF({im_inv}, 0), 1300))) AS invacc '
                f'FROM {im_tbl} WHERE {" AND ".join(where)}',
                params,
            )
            for row in cur.fetchall() or []:
                try:
                    ic = int(row[0])
                    out[ic] = resolve_item_inventory_gl_account(row[1])
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass
    for ic in uniq:
        out.setdefault(ic, '1300')
    return out


def _item_inventory_account_from_cache(
    inv_acc_cache: Dict[int, str],
    item_code: int,
) -> str:
    try:
        ic = int(item_code)
    except (TypeError, ValueError):
        return '1300'
    return resolve_item_inventory_gl_account(inv_acc_cache.get(ic, '1300'))


def _chart_of_accounts_code_set() -> Set[str]:
    out: Set[str] = set()
    for row in get_all_chart_of_accounts() or []:
        code = _norm_gl_account_code(row.get('code'))
        if code:
            out.add(code)
    return out


def _gl_account_code_is_invalid(code: Any, coa_codes: Set[str]) -> bool:
    norm = _norm_gl_account_code(code)
    if not norm:
        return True
    try:
        if int(float(norm)) <= 0:
            return True
    except (TypeError, ValueError):
        pass
    return norm not in coa_codes


def _validate_stock_adjustment_gl_account_codes(
    cur: Any,
    location_code: int,
    journal_lines: List[Dict[str, Any]],
    gl_rows: List[tuple],
    *,
    inv_acc_cache: Optional[Dict[int, str]] = None,
) -> Optional[str]:
    """Return error if any inventory or variance GL account is blank/zero or missing from COA."""
    coa_codes = _chart_of_accounts_code_set()
    if not coa_codes:
        return (
            'Chart of Accounts is empty. Add GL accounts (e.g. 1300 Inventory, 5199 Adjustment) '
            'before saving stock adjustment.'
        )

    errors: List[str] = []
    cols = _item_inventory_column_maps()
    if inv_acc_cache is None:
        item_codes: List[int] = []
        for row in journal_lines:
            try:
                ic = int(row.get('itemcode') or row.get('item_code') or 0)
            except (TypeError, ValueError):
                continue
            if ic > 0:
                item_codes.append(ic)
        inv_acc_cache = _batch_item_inventory_accounts_cur(cur, int(location_code), item_codes, cols)
    checked_items: Set[int] = set()
    for row in journal_lines:
        try:
            ic = int(row.get('itemcode') or row.get('item_code') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0 or ic in checked_items:
            continue
        checked_items.add(ic)
        inv_acc = _item_inventory_account_from_cache(inv_acc_cache, ic)
        if _gl_account_code_is_invalid(inv_acc, coa_codes):
            errors.append(
                f'Item {ic}: inventory account {inv_acc!r} is invalid or not in Chart of Accounts '
                f'(set INVENTORYACCOUNT in Item Master, typically 1300).'
            )

    variance = resolve_stk_adj_variance_account_codes()
    for label, key in (
        ('Stock increase (+) variance', 'increase'),
        ('Stock decrease (−) variance', 'decrease'),
        ('Opening stock import (+)', 'opening'),
    ):
        acc = str(variance.get(key) or '').strip()
        if acc and _gl_account_code_is_invalid(acc, coa_codes):
            errors.append(
                f'{label} account {acc!r} is invalid or not in Chart of Accounts '
                f'(Purchase → Stock Adjustment → Accounts Configuration).'
            )

    seen_gl: Set[str] = set()
    for acc, dr, cr, _rm in gl_rows or []:
        ac = _norm_gl_account_code(acc)
        if not ac or ac in seen_gl:
            continue
        if float(dr or 0) == 0 and float(cr or 0) == 0:
            continue
        seen_gl.add(ac)
        if _gl_account_code_is_invalid(ac, coa_codes):
            errors.append(f'GL account {ac!r} is invalid or not in Chart of Accounts.')

    if not errors:
        return None
    head = 'Cannot save stock adjustment — fix GL accounts first:'
    shown = errors[:8]
    extra = f' ({len(errors) - 8} more invalid account lines.)' if len(errors) > 8 else ''
    return head + '\n' + '\n'.join(f'• {e}' for e in shown) + extra


def validate_stock_adjustment_gl_accounts_cur(
    cur: Any,
    location_code: int,
    adj_no: Any,
    lines: List[Dict[str, Any]],
    *,
    opening_stock: bool = False,
) -> Optional[str]:
    """
    Pre-commit GL validation for stock adjustment save/approval post.
    Returns error message to block save (transaction rollback) when accounts are invalid.
    """
    if not _post_gl_enabled():
        return None
    journal_lines = _journal_lines_from_save_lines(lines)
    if not journal_lines:
        return None
    cols = _item_inventory_column_maps()
    item_codes: List[int] = []
    for row in journal_lines:
        try:
            ic = int(row.get('itemcode') or row.get('item_code') or 0)
        except (TypeError, ValueError):
            continue
        if ic > 0:
            item_codes.append(ic)
    inv_acc_cache = _batch_item_inventory_accounts_cur(cur, int(location_code), item_codes, cols)
    gl_rows, err = _build_stock_adjustment_gl_entry_rows(
        cur,
        location_code=int(location_code),
        adj_no=adj_no,
        journal_lines=journal_lines,
        inv_acc_cache=inv_acc_cache,
        opening_stock=bool(opening_stock),
    )
    if err:
        return err
    if not gl_rows:
        return None
    return _validate_stock_adjustment_gl_account_codes(
        cur, int(location_code), journal_lines, gl_rows, inv_acc_cache=inv_acc_cache,
    )


def _journal_lines_from_save_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines or [], start=1):
        try:
            item_int = int(float(ln.get('item_code') or 0))
        except (TypeError, ValueError):
            continue
        if item_int <= 0:
            continue
        try:
            adjust_qty = float(ln.get('adjust_qty') or 0)
        except (TypeError, ValueError):
            adjust_qty = 0.0
        try:
            base_qty = float(
                ln.get('base_qty')
                if ln.get('base_qty') is not None
                else adjust_qty
            )
        except (TypeError, ValueError):
            base_qty = 0.0
        if abs(base_qty) < 1e-09:
            continue
        try:
            factor = float(
                ln.get('conversionfactor')
                or ln.get('conversion_factor')
                or ln.get('factor')
                or ln.get('uomfactor')
                or 0
            )
        except (TypeError, ValueError):
            factor = 0.0
        if factor <= 0 and abs(adjust_qty) > 1e-12:
            factor = abs(base_qty) / abs(adjust_qty)
        if factor <= 0:
            factor = 1.0
        store = str(ln.get('store') or '').strip()
        # Line cost from UI is often alt/pack COSTPRICE — convert to base unit for GL.
        line_cost = float(ln.get('cost') or 0)
        base_unit_cost = line_cost
        if line_cost > 0 and factor > 1.0 + 1e-9:
            base_unit_cost = round(line_cost / factor, 6)
        row: Dict[str, Any] = {
            'lineno': idx,
            'slno': idx,
            'itemcode': item_int,
            'item_code': item_int,
            'uom': str(ln.get('uom') or 'NOS').strip() or 'NOS',
            'store': store,
            'warehouse_code': store,
            'quantity': adjust_qty,
            'adjust_qty': adjust_qty,
            'base_qty': base_qty,
            'conversionfactor': factor,
            'conversion_factor': factor,
            'factor': factor,
            'cost': line_cost,
            'costprice': line_cost,
        }
        if base_unit_cost > 0:
            row['averagecost'] = base_unit_cost
            row['average_cost'] = base_unit_cost
        lot_raw = ln.get('lot_id') or ln.get('lotid')
        if lot_raw is not None and str(lot_raw).strip():
            row['lot_id'] = lot_raw
        out.append(row)
    return out


def _build_stock_adjustment_gl_entry_rows(
    cur: Any,
    *,
    location_code: int,
    adj_no: Any,
    journal_lines: List[Dict[str, Any]],
    inv_acc_cache: Optional[Dict[int, str]] = None,
    opening_stock: bool = False,
) -> tuple:
    """
    Compute GL lines: inventory accounts (per item) vs stock-adjustment variance accounts.
    Returns (rows, error) where rows are (account_code, debit, credit, remarks).
    """
    inv_value: Dict[str, float] = defaultdict(float)
    cols = _item_inventory_column_maps()
    if inv_acc_cache is None:
        item_codes: List[int] = []
        for row in journal_lines:
            try:
                ic = int(row.get('itemcode') or row.get('item_code') or 0)
            except (TypeError, ValueError):
                continue
            if ic > 0:
                item_codes.append(ic)
        inv_acc_cache = _batch_item_inventory_accounts_cur(cur, int(location_code), item_codes, cols)
    cost_item_codes = list(inv_acc_cache.keys()) if inv_acc_cache else []
    item_cost_cache: Dict[int, float] = _batch_itemmaster_journal_cost_map(
        cur, int(location_code), cost_item_codes,
    )
    for row in journal_lines:
        try:
            ic = int(row.get('itemcode') or row.get('item_code') or 0)
            qty = float(row.get('base_qty') if row.get('base_qty') is not None else row.get('adjust_qty') or 0)
        except (TypeError, ValueError):
            continue
        if ic <= 0 or abs(qty) < 1e-07:
            continue
        inv_acc = _item_inventory_account_from_cache(inv_acc_cache, ic)
        avg_cost = _journal_average_cost_for_line(
            cur, int(location_code), row, item_cache=item_cost_cache,
        )
        inv_value[inv_acc] += qty * avg_cost

    total_increase = 0.0
    total_decrease = 0.0
    gl_rows: List[tuple] = []
    adj_label = _stk_adj_no_label(adj_no)
    for acc, amt in inv_value.items():
        if abs(amt) < 0.005:
            continue
        if amt > 0:
            remark = f'Opening stock #{adj_label} inventory' if opening_stock else f'Stock adjustment #{adj_label} inventory increase'
            gl_rows.append((acc, round(amt, 2), 0.0, remark))
            total_increase += amt
        else:
            gl_rows.append((acc, 0.0, round(abs(amt), 2), f'Stock adjustment #{adj_label} inventory decrease'))
            total_decrease += abs(amt)

    variance = resolve_stk_adj_variance_account_codes()
    if opening_stock:
        inc_acc = str(variance.get('opening') or '').strip()
        dec_acc = inc_acc
    else:
        inc_acc = str(variance.get('increase') or '').strip()
        dec_acc = str(variance.get('decrease') or '').strip()
    if total_increase > 0.005 and not inc_acc:
        if opening_stock:
            return ([], (
                'Opening stock account is not configured. '
                'Set it under Purchase → Stock Adjustment → Accounts Configuration (Opening Stock Import).'
            ))
        return ([], (
            'Stock increase (+) variance account is not configured. '
            'Set it under Purchase → Stock Adjustment → Accounts Configuration.'
        ))
    if total_decrease > 0.005 and not dec_acc:
        if opening_stock:
            return ([], (
                'Opening stock account is not configured. '
                'Set it under Purchase → Stock Adjustment → Accounts Configuration (Opening Stock Import).'
            ))
        return ([], (
            'Stock decrease (−) variance account is not configured. '
            'Set it under Purchase → Stock Adjustment → Accounts Configuration.'
        ))
    if total_increase > 0.005:
        offset_remark = (
            f'Opening stock #{adj_label} offset'
            if opening_stock
            else f'Stock adjustment #{adj_label} stock increase offset'
        )
        gl_rows.append((inc_acc, 0.0, round(total_increase, 2), offset_remark))
    if total_decrease > 0.005:
        dec_remark = (
            f'Opening stock #{adj_label} reversal offset'
            if opening_stock
            else f'Stock adjustment #{adj_label} stock decrease offset'
        )
        gl_rows.append((dec_acc, round(total_decrease, 2), 0.0, dec_remark))
    return (gl_rows, None)


def stock_adjustment_account_postings_for_pdf(
    location_code: int,
    adj_no: Any,
    save_lines: List[Dict[str, Any]],
    *,
    needs_approval: bool = False,
    gl_voucher_no: Optional[str] = None,
) -> Dict[str, Any]:
    """GL account lines for stock adjustment PDF (posted voucher or computed preview)."""
    variance = resolve_stk_adj_variance_account_codes()
    inc_code = str(variance.get('increase') or '').strip()
    dec_code = str(variance.get('decrease') or '').strip()
    coa_names = {
        str(r.get('code') or '').strip(): str(r.get('name') or '').strip()
        for r in (get_all_chart_of_accounts() or [])
    }
    vno = (gl_voucher_no or '').strip() or stock_adjustment_gl_voucher_no(location_code, adj_no)

    def _variance_meta() -> Dict[str, str]:
        return {
            'variance_increase_code': inc_code,
            'variance_increase_name': coa_names.get(inc_code, '') or '—',
            'variance_decrease_code': dec_code,
            'variance_decrease_name': coa_names.get(dec_code, '') or '—',
        }

    if not needs_approval:
        detail = get_gl_voucher_detail(vno)
        if detail and detail.get('lines'):
            out = {
                'voucher_no': str(detail.get('voucher_no') or vno),
                'is_posted': True,
                'is_preview': False,
                'lines': detail.get('lines') or [],
                'total_debit': float(detail.get('total_debit') or 0),
                'total_credit': float(detail.get('total_credit') or 0),
                'error': None,
            }
            out.update(_variance_meta())
            return out

    journal_lines = _journal_lines_from_save_lines(save_lines)
    if not journal_lines:
        out = {
            'voucher_no': vno,
            'is_posted': False,
            'is_preview': True,
            'lines': [],
            'total_debit': 0.0,
            'total_credit': 0.0,
            'error': None,
        }
        out.update(_variance_meta())
        return out

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                gl_rows, err = _build_stock_adjustment_gl_entry_rows(
                    cur,
                    location_code=int(location_code),
                    adj_no=adj_no,
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

    out = {
        'voucher_no': vno,
        'is_posted': False,
        'is_preview': True,
        'lines': lines_out,
        'total_debit': round(tdr, 2),
        'total_credit': round(tcr, 2),
        'error': err,
    }
    out.update(_variance_meta())
    return out


def _post_stock_adjustment_gl_cur(
    cur: Any,
    *,
    location_code: int,
    adj_no: Any,
    adj_date: str,
    journal_lines: List[Dict[str, Any]],
    posted_by: str,
    opening_stock: bool = False,
) -> Optional[str]:
    """GL voucher: Dr/Cr inventory accounts vs stock-adjustment variance account."""
    if not ensure_gl_tables():
        return 'GL tables are not available.'
    gl_rows, err = _build_stock_adjustment_gl_entry_rows(
        cur,
        location_code=int(location_code),
        adj_no=adj_no,
        journal_lines=journal_lines,
        opening_stock=bool(opening_stock),
    )
    if err:
        return err
    if not gl_rows:
        return None

    try:
        date_fmt = datetime.strptime(str(adj_date or '')[:10], '%Y-%m-%d').strftime('%d-%b-%Y').upper()
    except Exception:
        date_fmt = datetime.now().strftime('%d-%b-%Y').upper()

    gl_voucher_no = stock_adjustment_gl_voucher_no(location_code, adj_no)
    adj_label = _stk_adj_no_label(adj_no)
    gl_ref_no = adj_label[:50]
    gl_narration = (
        f'Opening stock #{adj_label}' if opening_stock else f'Stock adjustment #{adj_label}'
    )[:500]
    gl_user = (posted_by or '')[:50]
    cur.execute(f'DELETE FROM {GL_DTL_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(f'DELETE FROM {GL_HDR_TABLE} WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
    cur.execute(
        f"""
        INSERT INTO {GL_HDR_TABLE}
            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
        VALUES
            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'STOCK_ADJUSTMENT', :usr)
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


def post_stock_adjustment_accounting_cur(
    cur: Any,
    conn: Any,
    *,
    location_code: int,
    adj_no: Any,
    adj_date: str,
    lines: List[Dict[str, Any]],
    posted_by: str,
    reset_no: int,
    skip_gl_validate: bool = False,
    opening_stock: bool = False,
) -> Optional[str]:
    """
    ITEMJOURNAL + GL for a posted stock adjustment.
    Call only when inventory has been (or is being) posted in the same transaction.
    """
    journal_lines = _journal_lines_from_save_lines(lines)
    if not journal_lines:
        return None

    adj_ref = _stk_adj_no_numeric_ref(adj_no)

    if _post_gl_enabled() and not skip_gl_validate:
        gerr = validate_stock_adjustment_gl_accounts_cur(
            cur, int(location_code), adj_no, lines, opening_stock=bool(opening_stock),
        )
        if gerr:
            return gerr

    if _post_journal_enabled():
        ensure_itemjournal_surrogate_pk(conn)
        ensure_itemjournal_storage_id_column()
        ensure_itemjournal_warehouse_columns()
        ensure_itemjournal_batch_columns()
        ensure_itemjournal_averagecost_column()
        try:
            repost_itemjournal_stock_adjustment(
                cur, conn, int(location_code), int(reset_no), adj_ref, journal_lines,
                opening_stock=bool(opening_stock),
            )
        except Exception as ex:
            return f'Item journal: {ex}'

    if _post_gl_enabled():
        gl_err = _post_stock_adjustment_gl_cur(
            cur,
            location_code=int(location_code),
            adj_no=adj_no,
            adj_date=adj_date,
            journal_lines=journal_lines,
            posted_by=posted_by,
            opening_stock=bool(opening_stock),
        )
        if gl_err:
            return gl_err

    return None
