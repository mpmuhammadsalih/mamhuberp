"""
GRN pre-post validation engine (rule-based + optional risk scoring).

Mirrors the Journal Entry AI validation pattern: passed / warnings / errors / suggestions
with an overall risk score 0–100.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from db import (
    BIN_STOCK_TABLE,
    ITEM_LOT_TABLE,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _get_table_columns,
    _safe_rows,
    _table_exists,
    coerce_lpono,
    coerce_receiptno,
    ensure_bin_stock_tables,
    get_warehouse_storage_rows,
    is_item_batch_tracked,
    receiptno_is_valid,
)

# Thresholds (override via env)
COST_VARIANCE_WARN_PCT = float(os.environ.get('GRN_AI_COST_VARIANCE_WARN_PCT', '25') or 25)
COST_VARIANCE_BLOCK_PCT = float(os.environ.get('GRN_AI_COST_VARIANCE_BLOCK_PCT', '50') or 50)
QTY_ANOMALY_WARN_RATIO = float(os.environ.get('GRN_AI_QTY_ANOMALY_WARN_RATIO', '2.5') or 2.5)
QTY_ANOMALY_BLOCK_RATIO = float(os.environ.get('GRN_AI_QTY_ANOMALY_BLOCK_RATIO', '4.0') or 4.0)
PO_TOLERANCE_PCT = float(os.environ.get('GRN_AI_PO_TOLERANCE_PCT', '10') or 10)
NEAR_EXPIRY_DAYS = int(os.environ.get('GRN_AI_NEAR_EXPIRY_DAYS', '60') or 60)
SHELF_LIFE_WARN_RATIO = float(os.environ.get('GRN_AI_SHELF_LIFE_WARN_RATIO', '0.5') or 0.5)


def _risk_level(score: int) -> str:
    if score <= 30:
        return 'safe'
    if score <= 60:
        return 'warning'
    return 'high'


def _parse_date(s: Any) -> Optional[date]:
    if s is None or str(s).strip() == '':
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    t = str(s).strip()[:10]
    for fmt in ('%Y-%m-%d', '%d-%b-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _find_duplicate_invoice(
    supplier_code: int,
    invoice_no: str,
    except_receipt_no: Any,
    location_code: int,
    reset_no: int,
) -> Optional[Any]:
    inv = str(invoice_no or '').strip()
    if not inv or supplier_code <= 0:
        return None
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not hdr:
        return None
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset_col = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    no_col = _detect_column(hdr, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    sup_col = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    inv_col = _detect_column(hdr, ['INVOICENO', 'INVOICE_NO', 'invoiceno'])
    del_col = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    if not all([loc_col, no_col, sup_col, inv_col]):
        return None
    where = [
        f'{loc_col} = :loc',
        f'{sup_col} = :sup',
        f'{no_col} <> :excl',
        f'UPPER(LTRIM(RTRIM(TO_CHAR({inv_col})))) = UPPER(LTRIM(RTRIM(:invc)))',
    ]
    params: Dict[str, Any] = {
        'loc': location_code,
        'sup': supplier_code,
        'excl': coerce_receiptno(except_receipt_no),
        'invc': inv,
    }
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = reset_no
    if del_col:
        where.append(f"NVL({del_col},'N') <> 'Y'")
    q = f"SELECT {no_col} AS rno FROM {hdr} WHERE {' AND '.join(where)} AND ROWNUM = 1"
    try:
        _, rows = _fetch_rows(q, params)
        if rows and rows[0].get('rno') is not None:
            return rows[0]['rno']
    except Exception:
        pass
    return None


def _similar_invoice_receipts(
    supplier_code: int,
    invoice_amount: float,
    except_receipt_no: Any,
    location_code: int,
    reset_no: int,
    invoice_date: Optional[str],
) -> List[Any]:
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not hdr or invoice_amount <= 0:
        return []
    amt_col = _detect_column(hdr, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount'])
    sup_col = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    no_col = _detect_column(hdr, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset_col = _detect_column(hdr, ['RESETNO', 'RESET_NO', 'resetno'])
    date_col = _detect_column(hdr, ['INVOICEDATE', 'INVOICE_DATE', 'invoicedate'])
    if not all([amt_col, sup_col, no_col, loc_col]):
        return []
    tol = max(50.0, abs(invoice_amount) * 0.02)
    lo, hi = invoice_amount - tol, invoice_amount + tol
    where = [f'{loc_col} = :loc', f'{sup_col} = :sup', f'{no_col} <> :excl', f'NVL({amt_col},0) BETWEEN :lo AND :hi']
    params: Dict[str, Any] = {
        'loc': location_code,
        'sup': supplier_code,
        'excl': coerce_receiptno(except_receipt_no),
        'lo': lo,
        'hi': hi,
    }
    if reset_col:
        where.append(f'{reset_col} = :rn')
        params['rn'] = reset_no
    if date_col and invoice_date:
        inv_d = _parse_date(invoice_date)
        if inv_d:
            where.append(f'{date_col} BETWEEN :dfrom AND :dto')
            params['dfrom'] = inv_d - timedelta(days=7)
            params['dto'] = inv_d + timedelta(days=7)
    q = f"SELECT {no_col} AS rno FROM {hdr} WHERE {' AND '.join(where)} AND ROWNUM <= 5"
    try:
        _, rows = _fetch_rows(q, params)
        return [r['rno'] for r in rows or [] if r.get('rno') is not None]
    except Exception:
        return []


def _item_last_costs(item_code: int, location_code: int, supplier_code: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """last receipt rate, avg receipt rate (12 mo), last same-supplier rate."""
    dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not dtl or not hdr:
        im = _detect_table(['ITEMMASTER', 'itemmaster'])
        if im:
            cost_col = _detect_column(im, ['COSTPRICE', 'COST_PRICE', 'costprice', 'LANDINGCOST'])
            loc_col = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
            ic_col = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
            if cost_col and ic_col:
                w = [f'{ic_col} = :ic']
                p: Dict[str, Any] = {'ic': item_code}
                if loc_col:
                    w.append(f'{loc_col} = :loc')
                    p['loc'] = location_code
                rows = _safe_rows(f'SELECT NVL({cost_col},0) AS c FROM {im} WHERE {" AND ".join(w)} AND ROWNUM = 1', p) or []
                if rows:
                    return (float(rows[0].get('c') or 0) or None, None, None)
        return (None, None, None)
    ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    rate = _detect_column(dtl, ['RATE', 'rate'])
    loc_d = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    rno = _detect_column(dtl, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    if not ic or not rate or not rno:
        return (None, None, None)
    loc_h = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if hdr else None
    sup_h = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode']) if hdr else None
    dt_h = _detect_column(hdr, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate']) if hdr else None
    w = [f'{ic} = :ic', f'NVL({rate},0) > 0']
    p: Dict[str, Any] = {'ic': item_code, 'loc': location_code}
    if loc_d:
        w.append(f'{loc_d} = :loc')
    last_q = f"""
        SELECT NVL({rate},0) AS r FROM {dtl}
        WHERE {' AND '.join(w)}
        ORDER BY {rno} DESC
        FETCH FIRST 1 ROW ONLY
    """
    avg_q = f'SELECT AVG(NVL({rate},0)) AS ar FROM {dtl} WHERE {" AND ".join(w)}'
    sup_q = None
    if hdr and sup_h and loc_h and rno:
        sup_q = f"""
            SELECT NVL(d.{rate},0) AS r FROM {dtl} d
            INNER JOIN {hdr} h ON h.{rno} = d.{rno}
            WHERE d.{ic} = :ic AND NVL(d.{rate},0) > 0
              AND h.{loc_h} = :loc AND h.{sup_h} = :sup
            ORDER BY d.{rno} DESC
            FETCH FIRST 1 ROW ONLY
        """
    last_r = avg_r = sup_r = None
    try:
        rows = _safe_rows(last_q, p) or []
        if rows:
            last_r = float(rows[0].get('r') or 0) or None
    except Exception:
        pass
    try:
        rows = _safe_rows(avg_q, p) or []
        if rows and rows[0].get('ar') is not None:
            avg_r = float(rows[0]['ar']) or None
    except Exception:
        pass
    if sup_q and supplier_code > 0:
        try:
            rows = _safe_rows(sup_q, {**p, 'sup': supplier_code}) or []
            if rows:
                sup_r = float(rows[0].get('r') or 0) or None
        except Exception:
            pass
    return (last_r, avg_r, sup_r)


def _item_avg_grn_qty(item_code: int, location_code: int) -> Optional[float]:
    dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not dtl:
        return None
    ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    base = _detect_column(dtl, ['BASEQTY', 'BASE_QTY', 'baseqty'])
    qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not ic:
        return None
    q_expr = f'NVL({base}, NVL({qty},0))' if base and qty else (f'NVL({base},0)' if base else f'NVL({qty},0)')
    w = [f'{ic} = :ic']
    p: Dict[str, Any] = {'ic': item_code}
    if loc:
        w.append(f'{loc} = :loc')
        p['loc'] = location_code
    try:
        rows = _safe_rows(
            f'SELECT AVG({q_expr}) AS aq FROM {dtl} WHERE {" AND ".join(w)} AND {q_expr} > 0',
            p,
        ) or []
        if rows and rows[0].get('aq') is not None:
            v = float(rows[0]['aq'])
            return v if v > 0 else None
    except Exception:
        pass
    return None


def _lpo_line_qty_map(lpo_no: int, location_code: int, reset_no: int) -> Dict[int, float]:
    dtl = _detect_table(['LPODTL', 'lpodtl'])
    if not dtl or lpo_no <= 0:
        return {}
    ic = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    qty = _detect_column(dtl, ['INQUANTITY', 'INQUANTTITY', 'QUANTITY', 'quantity'])
    lpo_col = _detect_column(dtl, ['LPONO', 'LPO_NO', 'lpono'])
    loc = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    reset = _detect_column(dtl, ['RESETNO', 'RESET_NO', 'resetno'])
    if not ic or not qty or not lpo_col:
        return {}
    w = [f'{lpo_col} = :lpo']
    p: Dict[str, Any] = {'lpo': lpo_no}
    if loc:
        w.append(f'{loc} = :loc')
        p['loc'] = location_code
    if reset:
        w.append(f'NVL({reset},1) = :rn')
        p['rn'] = reset_no
    out: Dict[int, float] = {}
    try:
        for r in _safe_rows(f'SELECT {ic} AS ic, SUM(NVL({qty},0)) AS q FROM {dtl} WHERE {" AND ".join(w)} GROUP BY {ic}', p) or []:
            try:
                out[int(r['ic'])] = float(r.get('q') or 0)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    return out


def _batch_exists(location_code: int, item_code: int, batch_no: str) -> bool:
    if not _table_exists(ITEM_LOT_TABLE) or not batch_no:
        return False
    try:
        rows = _safe_rows(
            f"""
            SELECT 1 AS x FROM {ITEM_LOT_TABLE}
            WHERE LOCATIONCODE = :loc AND ITEMCODE = :ic
              AND UPPER(TRIM(BATCH_NO)) = UPPER(TRIM(:bn))
            AND ROWNUM = 1
            """,
            {'loc': location_code, 'ic': item_code, 'bn': batch_no[:80]},
        ) or []
        return bool(rows)
    except Exception:
        return False


def _suggest_bin(warehouse_id: Optional[int], item_code: int, location_code: int) -> Optional[str]:
    if not warehouse_id or not ensure_bin_stock_tables():
        return None
    try:
        wid = int(warehouse_id)
    except (TypeError, ValueError):
        return None
    bins = get_warehouse_storage_rows(wid, storage_type='BIN', db_key=None) or []
    if not bins:
        return None
    bs = BIN_STOCK_TABLE
    if not _table_exists(bs):
        for b in bins:
            code = str(b.get('code') or '').strip()
            if code:
                return code
        return None
    sid_col = 'STORAGE_ID'
    ic_col = 'ITEMCODE'
    qty_col = 'QTY'
    best_same: Optional[Tuple[float, str]] = None
    best_empty: Optional[str] = None
    for b in bins:
        sid = int(b.get('storage_id') or 0)
        code = str(b.get('code') or '').strip()
        if sid <= 0 or not code:
            continue
        try:
            rows = _safe_rows(
                f'SELECT NVL(SUM(NVL({qty_col},0)),0) AS tq FROM {bs} WHERE {sid_col} = :sid',
                {'sid': sid},
            ) or []
            total = float(rows[0].get('tq') or 0) if rows else 0.0
            same = _safe_rows(
                f'SELECT NVL({qty_col},0) AS q FROM {bs} WHERE {sid_col} = :sid AND {ic_col} = :ic AND ROWNUM = 1',
                {'sid': sid, 'ic': item_code},
            ) or []
            if same and float(same[0].get('q') or 0) > 0:
                if best_same is None or total < best_same[0]:
                    best_same = (total, code)
            elif total < 0.001 and best_empty is None:
                best_empty = code
        except Exception:
            continue
    if best_same:
        return best_same[1]
    if best_empty:
        return best_empty
    if bins:
        return str(bins[0].get('code') or '').strip() or None
    return None


def _barcode_item_candidates(barcode: str, location_code: int) -> List[Dict[str, Any]]:
    if not barcode:
        return []
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return []
    bc_cols = [
        c for c in (
            _detect_column(im, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid']),
            _detect_column(im, ['BARCODE', 'barcode']),
        )
        if c
    ]
    if not bc_cols:
        return []
    ic = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    nm = _detect_column(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    loc = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not ic:
        return []
    clauses = ' OR '.join(f'UPPER(TRIM(TO_CHAR({c}))) = UPPER(TRIM(:bc))' for c in bc_cols)
    w = [f'({clauses})']
    p: Dict[str, Any] = {'bc': barcode[:80]}
    if loc:
        w.append(f'{loc} = :loc')
        p['loc'] = location_code
    sel = f'{ic} AS itemcode'
    if nm:
        sel += f', {nm} AS itemname'
    try:
        return _safe_rows(f'SELECT {sel} FROM {im} WHERE {" AND ".join(w)} AND ROWNUM <= 5', p) or []
    except Exception:
        return []


def validate_grn_pre_post(
    payload: Dict[str, Any],
    *,
    location_code: Optional[int] = None,
    reset_no: int = 1,
) -> Dict[str, Any]:
    """
    Analyze a GRN draft before save/post.

    ``payload`` keys: receiptno, suppliercode, invoiceno, invoicedate, invoiceamount,
    lpono, warehouse_id, lines[].
    """
    loc_raw = location_code if location_code is not None else payload.get('locationcode')
    try:
        loc = int(loc_raw)
    except (TypeError, ValueError):
        return {
            'success': False,
            'error': 'Location code is required for validation.',
            'risk_score': 100,
            'risk_level': 'high',
            'blocking': True,
            'passed': [],
            'warnings': [],
            'errors': ['Location code is required.'],
            'suggestions': [],
            'line_issues': [],
            'line_suggestions': {},
            'actions': {'can_post': False, 'can_hold': True, 'can_submit_for_approval': False, 'can_reject': True},
        }
    rn = int(reset_no or 1)
    passed: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    suggestions: List[str] = []
    line_issues: List[Dict[str, Any]] = []
    line_suggestions: Dict[int, Dict[str, Any]] = {}

    receipt_no = coerce_receiptno(payload.get('receiptno'))
    if not receiptno_is_valid(receipt_no):
        receipt_no = coerce_receiptno(0)
    try:
        supplier_code = int(payload.get('suppliercode') or 0)
    except (TypeError, ValueError):
        supplier_code = 0
    invoice_no = str(payload.get('invoiceno') or '').strip()
    invoice_date = str(payload.get('invoicedate') or '').strip()
    try:
        invoice_amount = float(payload.get('invoiceamount') or 0)
    except (TypeError, ValueError):
        invoice_amount = 0.0
    lpo_no = coerce_lpono(payload.get('lpono'))
    if not str(lpo_no or '').strip() or str(lpo_no) == '0':
        lpo_no = coerce_lpono(0)
    try:
        warehouse_id = int(payload.get('warehouse_id') or 0) or None
    except (TypeError, ValueError):
        warehouse_id = None
    if warehouse_id is not None and warehouse_id <= 0:
        warehouse_id = None

    lines: List[Dict[str, Any]] = list(payload.get('lines') or [])
    if not supplier_code:
        errors.append('Supplier is required.')
    if not invoice_no:
        errors.append('Invoice number is required.')
    if not lines:
        errors.append('At least one receipt line is required.')
    else:
        passed.append(f'{len(lines)} line(s) present.')

    dup = _find_duplicate_invoice(supplier_code, invoice_no, receipt_no, loc, rn)
    if dup:
        errors.append(f'Duplicate supplier invoice: already used on GRN {dup}.')
    else:
        passed.append('No duplicate supplier invoice number for this branch.')

    similar = _similar_invoice_receipts(supplier_code, invoice_amount, receipt_no, loc, rn, invoice_date)
    if similar:
        warnings.append(f'Similar invoice amount/date on GRN(s): {", ".join(str(x) for x in similar)}.')

    lpo_map = _lpo_line_qty_map(lpo_no, loc, rn) if lpo_no > 0 else {}
    if lpo_no > 0:
        passed.append(f'Linked to LPO {lpo_no} — PO tolerance {PO_TOLERANCE_PCT:.0f}%.')
    else:
        suggestions.append('Link an LPO when receiving against a purchase order.')

    seen_batches: Set[Tuple[int, str]] = set()
    seen_barcodes: Dict[str, int] = {}
    now = datetime.now()
    hour = now.hour

    for idx, line in enumerate(lines, 1):
        try:
            item_code = int(line.get('itemcode') or line.get('item_code') or 0)
        except (TypeError, ValueError):
            item_code = 0
        if item_code <= 0:
            continue
        try:
            rate = float(line.get('rate') or 0)
        except (TypeError, ValueError):
            rate = 0.0
        try:
            base_qty = float(line.get('baseqty') or line.get('stock_qty_base') or 0)
        except (TypeError, ValueError):
            base_qty = 0.0
        if base_qty <= 0:
            try:
                qty = float(line.get('quantity') or 0)
                cf = float(line.get('conversionfactor') or 1) or 1.0
                bonus = float(line.get('bonus') or 0)
                base_qty = qty * cf + bonus
            except (TypeError, ValueError):
                base_qty = 0.0
        batch_no = str(line.get('batch_no') or line.get('batchno') or '').strip()
        barcode = str(line.get('barcode') or line.get('manufacturerid') or '').strip()
        exp_d = _parse_date(line.get('expiry_date') or line.get('expirydate'))
        mfg_d = _parse_date(line.get('mfg_date') or line.get('mfgdate'))

        # Cost variance
        last_c, avg_c, sup_c = _item_last_costs(item_code, loc, supplier_code)
        ref = sup_c or last_c or avg_c
        if ref and ref > 0 and rate > 0:
            var_pct = ((rate - ref) / ref) * 100.0
            msg = f'Line {idx}: cost {rate:.3f} vs ref {ref:.3f} ({var_pct:+.1f}%).'
            line_issues.append({'line': idx, 'itemcode': item_code, 'code': 'cost_variance', 'severity': 'warning', 'message': msg, 'variance_pct': round(var_pct, 1)})
            if abs(var_pct) >= COST_VARIANCE_BLOCK_PCT:
                errors.append(msg + ' Exceeds blocking threshold.')
            elif abs(var_pct) >= COST_VARIANCE_WARN_PCT:
                warnings.append(msg)
            else:
                passed.append(f'Line {idx}: cost within normal variance.')
        elif rate <= 0:
            warnings.append(f'Line {idx}: zero rate.')

        # Quantity anomaly
        avg_q = _item_avg_grn_qty(item_code, loc)
        if avg_q and base_qty > 0:
            ratio = base_qty / avg_q
            if ratio >= QTY_ANOMALY_BLOCK_RATIO:
                warnings.append(f'Line {idx}: qty {base_qty:.3g} is {ratio:.0f}× historical avg ({avg_q:.3g}).')
                line_issues.append({'line': idx, 'itemcode': item_code, 'code': 'qty_anomaly', 'severity': 'warning', 'message': f'Quantity {ratio:.0f}× normal', 'ratio': round(ratio, 2)})
            elif ratio >= QTY_ANOMALY_WARN_RATIO:
                warnings.append(f'Line {idx}: qty {base_qty:.3g} is {ratio:.1f}× historical avg ({avg_q:.3g}).')

        # PO match
        if lpo_map and item_code in lpo_map:
            po_q = float(lpo_map[item_code] or 0)
            if po_q > 0:
                over = base_qty - po_q * (1 + PO_TOLERANCE_PCT / 100.0)
                if over > 0.0001:
                    warnings.append(f'Line {idx}: received {base_qty:.3g} exceeds PO {po_q:.3g} (+{PO_TOLERANCE_PCT:.0f}% tolerance).')
                else:
                    passed.append(f'Line {idx}: within PO quantity tolerance.')

        # Batch
        if batch_no:
            key = (item_code, batch_no.upper())
            if key in seen_batches:
                errors.append(f'Line {idx}: duplicate batch "{batch_no}" on this GRN.')
            seen_batches.add(key)
            if _batch_exists(loc, item_code, batch_no):
                warnings.append(f'Line {idx}: batch "{batch_no}" already exists for this item.')
            if is_item_batch_tracked(item_code, loc) and not exp_d:
                errors.append(f'Line {idx}: expiry date required for batch-tracked item.')
            if mfg_d and exp_d and mfg_d >= exp_d:
                errors.append(f'Line {idx}: manufacturing date must be before expiry.')
            if exp_d:
                days_left = (exp_d - date.today()).days
                if days_left < 0:
                    errors.append(f'Line {idx}: batch already expired ({exp_d}).')
                elif days_left <= NEAR_EXPIRY_DAYS:
                    warnings.append(f'Line {idx}: near expiry ({days_left} days left).')
                if mfg_d and exp_d:
                    shelf = (exp_d - mfg_d).days
                    if shelf > 0 and days_left < shelf * SHELF_LIFE_WARN_RATIO:
                        warnings.append(f'Line {idx}: short shelf life vs batch window ({days_left}/{shelf} days).')

        # Barcode
        if barcode:
            if barcode in seen_barcodes:
                warnings.append(f'Line {idx}: barcode "{barcode}" scanned more than once.')
            seen_barcodes[barcode] = idx
            if item_code:
                cands = _barcode_item_candidates(barcode, loc)
                if not cands:
                    warnings.append(f'Line {idx}: barcode not found on item master.')
                elif len(cands) == 1 and int(cands[0].get('itemcode') or 0) != item_code:
                    alt = cands[0]
                    nm = str(alt.get('itemname') or alt.get('itemcode') or '')
                    warnings.append(f'Line {idx}: barcode matches item {alt.get("itemcode")} ({nm}), not {item_code}.')
                    suggestions.append(f'Line {idx}: did you mean item {alt.get("itemcode")}?')

        # Bin suggestion
        wh_line = line.get('warehouse_id') or warehouse_id
        try:
            wh_line_i = int(wh_line) if wh_line not in (None, '') else None
        except (TypeError, ValueError):
            wh_line_i = warehouse_id
        sug_bin = _suggest_bin(wh_line_i, item_code, loc)
        if sug_bin:
            line_suggestions[idx] = {'suggested_bin': sug_bin}
            if not line.get('storage_id'):
                suggestions.append(f'Line {idx}: suggested bin {sug_bin}.')

    # Fraud / pattern
    if hour < 6 or hour >= 23:
        warnings.append('Posting outside normal business hours — review for unusual activity.')
    high_var_lines = [x for x in line_issues if x.get('code') == 'cost_variance' and abs(float(x.get('variance_pct') or 0)) >= COST_VARIANCE_WARN_PCT]
    if len(high_var_lines) >= 3:
        warnings.append(f'{len(high_var_lines)} lines with high cost variance — possible price manipulation.')
    if invoice_amount > 500000:
        warnings.append('High-value GRN — manager approval recommended.')

    risk_score = min(100, len(errors) * 35 + len(warnings) * 10)
    confidence = max(0, 100 - len(errors) * 30 - len(warnings) * 8)
    level = _risk_level(risk_score)
    blocking = len(errors) > 0

    actions = {
        'can_post': not blocking,
        'can_hold': True,
        'can_submit_for_approval': True,
        'can_reject': True,
    }
    if level == 'high' and not blocking:
        actions['can_post'] = False
        actions['can_submit_for_approval'] = True

    return {
        'success': True,
        'risk_score': risk_score,
        'risk_level': level,
        'confidence': confidence,
        'blocking': blocking,
        'passed': passed,
        'warnings': warnings,
        'errors': errors,
        'suggestions': suggestions[:30],
        'line_issues': line_issues,
        'line_suggestions': line_suggestions,
        'actions': actions,
        'thresholds': {
            'cost_variance_warn_pct': COST_VARIANCE_WARN_PCT,
            'cost_variance_block_pct': COST_VARIANCE_BLOCK_PCT,
            'qty_anomaly_warn_ratio': QTY_ANOMALY_WARN_RATIO,
            'po_tolerance_pct': PO_TOLERANCE_PCT,
        },
    }
