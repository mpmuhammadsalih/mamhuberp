"""Excel import helpers for Stock Adjustment lines."""
from __future__ import annotations

import io
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from db import (
    WAREHOUSE_STOCK_TABLE,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _safe_rows,
    _table_exists,
    ensure_warehouse_stock_table,
    get_item_store_inventory,
    get_item_store_rows_from_itemmaster,
    get_warehouse_master_store_picker_rows,
    list_warehouses_for_location,
    resolve_warehouse_master_table,
)

STK_ADJ_IMPORT_MAX_ROWS = 1000
STK_ADJ_IMPORT_MAX_FILE_BYTES = 5 * 1024 * 1024


def parse_stk_adj_xlsx(raw: bytes, *, max_rows: int = STK_ADJ_IMPORT_MAX_ROWS) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """First sheet: row 1 = headers, row 2+ = data."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], 'Excel import requires openpyxl (pip install openpyxl).')
    try:
        bio = io.BytesIO(raw)
        wb = load_workbook(bio, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows_it = ws.iter_rows(values_only=True)
            first = next(rows_it, None)
            if first is None:
                return ([], 'The worksheet is empty.')
            headers: List[str] = []
            for c in first:
                if c is None:
                    headers.append('')
                else:
                    s = str(c).strip()
                    headers.append(s if s else '')
            out_rows: List[Dict[str, Any]] = []
            for row in rows_it:
                if len(out_rows) >= max_rows:
                    break
                rd: Dict[str, Any] = {}
                empty = True
                for i, h in enumerate(headers):
                    if not h:
                        continue
                    v = row[i] if i < len(row) else None
                    if v is not None and str(v).strip() != '':
                        empty = False
                    rd[h] = v
                if not empty:
                    out_rows.append(rd)
            return (out_rows, None)
        finally:
            try:
                wb.close()
            except Exception:
                pass
    except Exception as exc:
        return ([], str(exc))


def _norm_hdr(key: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(key or '').strip().lower())


def _cell(row: Dict[str, Any], *aliases: str) -> Any:
    if not row:
        return None
    norm_map = {_norm_hdr(k): v for k, v in row.items() if k}
    for alias in aliases:
        nk = _norm_hdr(alias)
        if nk in norm_map:
            return norm_map[nk]
    return None


def _parse_float(val: Any) -> Optional[float]:
    if val is None or str(val).strip() == '':
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        s = str(val).strip().replace(',', '')
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None


def _parse_int(val: Any) -> Optional[int]:
    f = _parse_float(val)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _lookup_item_master(
    location_code: int,
    *,
    item_code: Optional[int] = None,
    barcode: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not tbl:
        return None
    code_col = _detect_column(tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    name_col = _detect_column(tbl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    uom_col = _detect_column(tbl, ['BASEUOM', 'BASE_UOM', 'baseuom'])
    barcode_col = _detect_column(tbl, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'BARCODE', 'barcode'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not code_col:
        return None
    where = ['1=1']
    params: Dict[str, Any] = {}
    if loc_col:
        where.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    if item_code and int(item_code) > 0:
        where.append(f'{code_col} = :icode')
        params['icode'] = int(item_code)
    elif barcode and str(barcode).strip():
        if not barcode_col:
            return None
        where.append(f"TRIM(UPPER(TO_CHAR({barcode_col}))) = TRIM(UPPER(:bc))")
        params['bc'] = str(barcode).strip()[:50]
    else:
        return None
    sel = [f'{code_col} AS itemcode']
    if name_col:
        sel.append(f'{name_col} AS itemname')
    if uom_col:
        sel.append(f'{uom_col} AS baseuom')
    q = f"SELECT {', '.join(sel)} FROM {tbl} WHERE {' AND '.join(where)}"
    try:
        _, rows = _fetch_rows(q, params)
        if not rows:
            return None
        r = rows[0]
        return {
            'itemcode': int(float(r.get('itemcode') or 0)),
            'itemname': str(r.get('itemname') or '').strip(),
            'baseuom': str(r.get('baseuom') or 'NOS').strip() or 'NOS',
        }
    except Exception:
        return None


def _store_row_list(store_rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return list(store_rows or [])


def _resolve_store_stock_from_rows(store_rows: List[Dict[str, Any]], store: str) -> Tuple[str, float]:
    store_u = str(store or '').strip().upper()
    current_qty = 0.0
    resolved_store = store_u
    if store_u:
        for r in store_rows or []:
            rs = str(r.get('store') or r.get('itemlocation') or '').strip().upper()
            if rs == store_u:
                current_qty = float(r.get('stock') or 0)
                resolved_store = rs
                break
    elif store_rows:
        best = max(store_rows, key=lambda x: float(x.get('stock') or 0))
        current_qty = float(best.get('stock') or 0)
        resolved_store = str(best.get('store') or best.get('itemlocation') or '').strip().upper()
    return resolved_store, current_qty


def _stores_from_rows(store_rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for r in store_rows or []:
        st = str(r.get('store') or r.get('itemlocation') or '').strip().upper()
        if st and st not in out:
            out.append(st)
    return out


def _chunked(seq: List[Any], size: int) -> List[List[Any]]:
    if size <= 0:
        return [seq]
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _batch_lookup_items(
    location_code: int,
    item_codes: List[int],
    barcodes: List[str],
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Prefetch ITEMMASTER rows keyed by item code and upper barcode."""
    by_code: Dict[int, Dict[str, Any]] = {}
    by_barcode: Dict[str, Dict[str, Any]] = {}
    tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not tbl:
        return by_code, by_barcode
    code_col = _detect_column(tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    name_col = _detect_column(tbl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    uom_col = _detect_column(tbl, ['BASEUOM', 'BASE_UOM', 'baseuom'])
    barcode_col = _detect_column(tbl, ['MANUFACTURERID', 'MANUFACTURER_ID', 'manufacturerid', 'BARCODE', 'barcode'])
    loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    cost_col = _detect_column(tbl, ['COSTPRICE', 'COST_PRICE', 'costprice'])
    if not code_col:
        return by_code, by_barcode
    sel = [f'{code_col} AS itemcode']
    if name_col:
        sel.append(f'{name_col} AS itemname')
    if uom_col:
        sel.append(f'{uom_col} AS baseuom')
    if barcode_col:
        sel.append(f'{barcode_col} AS barcode')
    if cost_col:
        sel.append(f'{cost_col} AS costprice')
    uniq_codes = sorted({int(c) for c in item_codes if c and int(c) > 0})
    uniq_bcs = sorted({str(b).strip().upper() for b in barcodes if str(b or '').strip()})
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if loc_col:
        where_parts.append(f'{loc_col} = :loc')
        params['loc'] = int(location_code)
    or_parts: List[str] = []
    for ci, chunk in enumerate(_chunked(uniq_codes, 400)):
        keys = [f'ic_{ci}_{i}' for i in range(len(chunk))]
        binds = ','.join(f':{k}' for k in keys)
        for k, v in zip(keys, chunk):
            params[k] = int(v)
        or_parts.append(f'{code_col} IN ({binds})')
    for bi, chunk in enumerate(_chunked(uniq_bcs, 400)):
        if not barcode_col:
            break
        keys = [f'bc_{bi}_{i}' for i in range(len(chunk))]
        binds = ','.join(f':{k}' for k in keys)
        for k, v in zip(keys, chunk):
            params[k] = str(v)[:50]
        or_parts.append(f'TRIM(UPPER(TO_CHAR({barcode_col}))) IN ({binds})')
    if not or_parts:
        return by_code, by_barcode
    where_parts.append('(' + ' OR '.join(or_parts) + ')')
    q = f"SELECT {', '.join(sel)} FROM {tbl} WHERE {' AND '.join(where_parts)}"
    try:
        _, rows = _fetch_rows(q, params)
    except Exception:
        return by_code, by_barcode
    for r in rows or []:
        try:
            ic = int(float(r.get('itemcode') or 0))
        except (TypeError, ValueError):
            continue
        if ic <= 0:
            continue
        item = {
            'itemcode': ic,
            'itemname': str(r.get('itemname') or '').strip(),
            'baseuom': str(r.get('baseuom') or 'NOS').strip() or 'NOS',
        }
        if r.get('costprice') is not None:
            try:
                item['costprice'] = float(r.get('costprice') or 0)
            except (TypeError, ValueError):
                item['costprice'] = 0.0
        by_code[ic] = item
        bc = str(r.get('barcode') or '').strip().upper()
        if bc:
            by_barcode[bc] = item
    return by_code, by_barcode


def _batch_store_rows_by_item(location_code: int, item_codes: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Prefetch warehouse/store rows for many items (avoids N+1 during Excel import)."""
    out: Dict[int, List[Dict[str, Any]]] = {}
    uniq = sorted({int(c) for c in item_codes if c and int(c) > 0})
    if not uniq:
        return out
    if ensure_warehouse_stock_table() and _table_exists(WAREHOUSE_STOCK_TABLE):
        wm_tbl = resolve_warehouse_master_table()
        for ci, chunk in enumerate(_chunked(uniq, 400)):
            keys = [f'ic_{ci}_{i}' for i in range(len(chunk))]
            binds = ','.join(f':{k}' for k in keys)
            params: Dict[str, Any] = {'loc': int(location_code)}
            for k, v in zip(keys, chunk):
                params[k] = int(v)
            if wm_tbl:
                q = f"""
                    SELECT
                        ws.ITEMCODE AS itemcode,
                        TO_CHAR(wm.WAREHOUSE_ID) AS code,
                        TRIM(wm.WAREHOUSE_CODE) AS store,
                        TRIM(wm.WAREHOUSE_NAME) AS description,
                        NVL(ws.QTY, 0) AS stock,
                        wm.WAREHOUSE_ID AS warehouse_id
                    FROM {WAREHOUSE_STOCK_TABLE} ws
                    INNER JOIN {wm_tbl} wm
                      ON wm.WAREHOUSE_ID = ws.WAREHOUSE_ID
                     AND wm.LOCATIONCODE = ws.LOCATIONCODE
                    WHERE ws.LOCATIONCODE = :loc
                      AND ws.ITEMCODE IN ({binds})
                      AND NVL(wm.IS_ACTIVE, 'Y') = 'Y'
                      AND NVL(ws.QTY, 0) <> 0
                    ORDER BY ws.ITEMCODE, UPPER(TRIM(wm.WAREHOUSE_CODE))
                """
            else:
                q = f"""
                    SELECT
                        ws.ITEMCODE AS itemcode,
                        TO_CHAR(ws.WAREHOUSE_ID) AS code,
                        TO_CHAR(ws.WAREHOUSE_ID) AS store,
                        '' AS description,
                        NVL(ws.QTY, 0) AS stock,
                        ws.WAREHOUSE_ID AS warehouse_id
                    FROM {WAREHOUSE_STOCK_TABLE} ws
                    WHERE ws.LOCATIONCODE = :loc
                      AND ws.ITEMCODE IN ({binds})
                      AND NVL(ws.QTY, 0) <> 0
                    ORDER BY ws.ITEMCODE, ws.WAREHOUSE_ID
                """
            try:
                rows = _safe_rows(q, params) or []
            except Exception:
                rows = []
            for r in rows:
                try:
                    ic = int(float(r.get('itemcode') or 0))
                except (TypeError, ValueError):
                    continue
                if ic <= 0:
                    continue
                out.setdefault(ic, []).append(dict(r))
    missing = [ic for ic in uniq if ic not in out]
    if missing:
        im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
        wm_tbl = resolve_warehouse_master_table()
        code_col = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) if im else None
        loc_col = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if im else None
        dw_col = 'DEFAULT_WAREHOUSE_ID'
        cu_col = _detect_column(im, ['CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK']) if im else None
        im_cols = {c.upper() for c in (_get_table_columns(im) or [])} if im else set()
        if im and code_col and loc_col and dw_col in im_cols and wm_tbl:
            for ci, chunk in enumerate(_chunked(missing, 400)):
                keys = [f'mic_{ci}_{i}' for i in range(len(chunk))]
                binds = ','.join(f':{k}' for k in keys)
                params: Dict[str, Any] = {'loc': int(location_code)}
                for k, v in zip(keys, chunk):
                    params[k] = int(v)
                qty_sql = f'NVL(im.{cu_col}, 0)' if cu_col else '0'
                q = f"""
                    SELECT im.{code_col} AS itemcode,
                           TRIM(wm.WAREHOUSE_CODE) AS store,
                           TO_CHAR(wm.WAREHOUSE_ID) AS code,
                           TRIM(wm.WAREHOUSE_NAME) AS description,
                           {qty_sql} AS stock,
                           wm.WAREHOUSE_ID AS warehouse_id
                    FROM {im} im
                    INNER JOIN {wm_tbl} wm
                      ON wm.WAREHOUSE_ID = im.{dw_col}
                     AND wm.LOCATIONCODE = im.{loc_col}
                    WHERE im.{loc_col} = :loc
                      AND im.{code_col} IN ({binds})
                      AND NVL(wm.IS_ACTIVE, 'Y') = 'Y'
                """
                try:
                    rows = _safe_rows(q, params) or []
                except Exception:
                    rows = []
                for r in rows:
                    try:
                        ic = int(float(r.get('itemcode') or 0))
                    except (TypeError, ValueError):
                        continue
                    if ic <= 0:
                        continue
                    out.setdefault(ic, []).append(dict(r))
        still_missing = [ic for ic in missing if ic not in out]
        for ic in still_missing:
            rows = get_item_store_inventory(int(location_code), int(ic))
            if not rows:
                try:
                    rows = get_item_store_rows_from_itemmaster(int(ic), int(location_code)) or []
                except Exception:
                    rows = []
            if rows:
                out[ic] = [dict(r) for r in rows]
    return out


def _get_table_columns(tbl: str) -> List[str]:
    from db import _get_table_columns as _gtc
    try:
        return list(_gtc(tbl) or [])
    except Exception:
        return []


def _batch_uom_factor_map(
    location_code: int,
    item_codes: List[int],
    items_by_code: Dict[int, Dict[str, Any]],
) -> Dict[int, Dict[str, float]]:
    """Map item_code -> {UOM: factor} including base UOM and alternate UOM rows."""
    out: Dict[int, Dict[str, float]] = {}
    uniq = sorted({int(c) for c in item_codes if c and int(c) > 0})
    for ic in uniq:
        base = str((items_by_code.get(ic) or {}).get('baseuom') or 'NOS').strip().upper() or 'NOS'
        out.setdefault(ic, {})[base] = 1.0
    alt_tbl = _detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap', 'ITEM_ALTERNATE_UOM_MAP'])
    if not alt_tbl or not uniq:
        return out
    item_col = _detect_column(alt_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    uom_col = _detect_column(alt_tbl, ['ALTERNATEUOMCODE', 'ALTERNATE_UOM_CODE', 'alternateuomcode'])
    fac_col = _detect_column(alt_tbl, ['FACTOR', 'CONVERSIONFACTOR', 'UOMFACTOR'])
    loc_col = _detect_column(alt_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not item_col or not uom_col:
        return out
    for ci, chunk in enumerate(_chunked(uniq, 400)):
        keys = [f'uic_{ci}_{i}' for i in range(len(chunk))]
        binds = ','.join(f':{k}' for k in keys)
        params: Dict[str, Any] = {'loc': int(location_code)}
        for k, v in zip(keys, chunk):
            params[k] = int(v)
        fac_sql = f'NVL({alt_tbl}.{fac_col}, 1)' if fac_col else '1'
        where = [f'{alt_tbl}.{item_col} IN ({binds})']
        if loc_col:
            where.append(f'{alt_tbl}.{loc_col} = :loc')
        q = f"""
            SELECT {alt_tbl}.{item_col} AS itemcode,
                   TRIM({alt_tbl}.{uom_col}) AS uom,
                   {fac_sql} AS factor
            FROM {alt_tbl}
            WHERE {' AND '.join(where)}
        """
        try:
            rows = _safe_rows(q, params) or []
        except Exception:
            rows = []
        for r in rows:
            try:
                ic = int(float(r.get('itemcode') or 0))
            except (TypeError, ValueError):
                continue
            uom = str(r.get('uom') or '').strip().upper()
            if ic <= 0 or not uom:
                continue
            try:
                factor = float(r.get('factor') or 1.0)
            except (TypeError, ValueError):
                factor = 1.0
            out.setdefault(ic, {})[uom] = factor if factor > 0 else 1.0
    return out


def _branch_warehouse_codes(location_code: int) -> frozenset:
    """Warehouse codes allowed on stock adjustment — same source as F1 picker API."""
    codes: set = set()
    try:
        picker_rows, _transit = get_warehouse_master_store_picker_rows()
        for row in picker_rows or []:
            code = str(row.get('code') or '').strip().upper()
            if code:
                codes.add(code)
    except Exception:
        codes = set()
    if not codes:
        for wh in list_warehouses_for_location(int(location_code), active_only=True) or []:
            code = str(wh.get('warehouse_code') or '').strip().upper()
            if code:
                codes.add(code)
    return frozenset(codes)


def _prefetch_import_context(
    rows: List[Dict[str, Any]],
    location_code: int,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[int, List[Dict[str, Any]]], frozenset]:
    item_codes: List[int] = []
    barcodes: List[str] = []
    for raw in rows or []:
        ic_raw = _cell(raw, 'ItemCode', 'Item Code', 'ITEMCODE', 'Code', 'Item')
        bc_raw = _cell(raw, 'Barcode', 'BARCODE', 'ManufacturerId', 'MANUFACTURERID', 'RawabiCode')
        ic = _parse_int(ic_raw)
        bc = str(bc_raw or '').strip()
        if ic and ic > 0:
            item_codes.append(int(ic))
        elif bc:
            barcodes.append(bc)
    by_code, by_barcode = _batch_lookup_items(int(location_code), item_codes, barcodes)
    all_codes = set(by_code.keys())
    for ic in item_codes:
        if ic > 0:
            all_codes.add(int(ic))
    store_by_item = _batch_store_rows_by_item(int(location_code), sorted(all_codes))
    branch_wh = _branch_warehouse_codes(int(location_code))
    return by_code, by_barcode, store_by_item, branch_wh


def build_lines_from_import_rows(
    rows: List[Dict[str, Any]],
    *,
    location_code: int,
    uom_factor_fn: Callable[[Any, Optional[str]], float],
    cost_fn: Callable[[Any, Optional[str]], float],
    uom_valid_fn: Callable[[Any, Optional[str]], bool],
    max_rows: int = STK_ADJ_IMPORT_MAX_ROWS,
    uom_factor_map: Optional[Dict[int, Dict[str, float]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse spreadsheet rows into stock adjustment line dicts (includes invalid rows with field_errors)."""
    lines: List[Dict[str, Any]] = []
    errors: List[str] = []
    items_by_code, items_by_barcode, store_by_item, branch_wh_codes = _prefetch_import_context(rows, int(location_code))
    if uom_factor_map is None:
        uom_factor_map = _batch_uom_factor_map(int(location_code), list(items_by_code.keys()), items_by_code)

    def _uom_valid(item_code: int, uom: str) -> bool:
        u = str(uom or '').strip().upper()
        if not u or item_code <= 0:
            return False
        mapped = uom_factor_map.get(int(item_code))
        if mapped and u in mapped:
            return True
        return bool(uom_valid_fn(item_code, uom))

    def _uom_factor(item_code: int, uom: str) -> float:
        u = str(uom or '').strip().upper()
        if item_code > 0 and u:
            fac = (uom_factor_map.get(int(item_code)) or {}).get(u)
            if fac is not None:
                return float(fac)
        return float(uom_factor_fn(item_code, uom) or 1.0)
    sheet_row = 1
    processed = 0
    for raw in rows or []:
        sheet_row += 1
        if processed >= max_rows:
            errors.append(f'Stopped after {max_rows} data rows.')
            break
        ic_raw = _cell(raw, 'ItemCode', 'Item Code', 'ITEMCODE', 'Code', 'Item')
        bc_raw = _cell(raw, 'Barcode', 'BARCODE', 'ManufacturerId', 'MANUFACTURERID', 'RawabiCode')
        uom_raw = _cell(raw, 'UOM', 'Unit', 'UnitOfMeasurement', 'UNITOFMEASUREMENT')
        store_raw = _cell(raw, 'Store', 'STORE', 'Warehouse', 'ItemLocation')
        adj_raw = _cell(raw, 'AdjustQty', 'Adjust Qty', 'ADJUSTQTY', 'Qty', 'Quantity', 'Difference', 'Diff')
        lot_raw = _cell(raw, 'LotId', 'Lot ID', 'Lot', 'LOTID', 'LOT')

        ic = _parse_int(ic_raw)
        bc = str(bc_raw or '').strip()
        if (not ic or ic <= 0) and not bc:
            continue
        processed += 1

        field_errors: Dict[str, str] = {}
        item: Optional[Dict[str, Any]] = None
        if ic and ic > 0:
            item = items_by_code.get(int(ic))
        if not item and bc:
            item = items_by_barcode.get(bc.strip().upper())
        if not item:
            item = _lookup_item_master(
                int(location_code),
                item_code=ic if ic and ic > 0 else None,
                barcode=bc or None,
            )
        if not item:
            ref = str(ic or bc or '').strip()
            field_errors['item_code'] = f'Item not found ({ref}).'
            item_code = int(ic or 0)
            item_name = ''
            uom = str(uom_raw or 'NOS').strip() or 'NOS'
            store = str(store_raw or '').strip().upper()
            current_qty = 0.0
            cost = 0.0
            store_rows: List[Dict[str, Any]] = []
        else:
            item_code = int(item.get('itemcode') or 0)
            item_name = str(item.get('itemname') or '').strip()
            uom = str(uom_raw or item.get('baseuom') or 'NOS').strip() or 'NOS'
            store_rows = _store_row_list(store_by_item.get(item_code))
            store, current_qty = _resolve_store_stock_from_rows(store_rows, str(store_raw or '').strip())
            if item.get('costprice') is not None:
                cost = float(item.get('costprice') or 0)
            else:
                cost = float(cost_fn(item_code, uom) or 0)
            if not _uom_valid(item_code, uom):
                field_errors['uom'] = f'UOM "{uom}" is not defined for item {item_code}.'
            store_req = str(store_raw or '').strip().upper()
            if not store and not store_req:
                field_errors['store'] = 'Store is required for this item.'
            elif store_req:
                if branch_wh_codes:
                    if store_req not in branch_wh_codes:
                        field_errors['store'] = f'Warehouse "{store_req}" is not valid for this branch.'
                    elif not store:
                        store = store_req
                else:
                    allowed = _stores_from_rows(store_rows)
                    if allowed and store_req not in allowed:
                        field_errors['store'] = f'Store "{store_req}" is not valid for item {item_code}.'
                    elif not store:
                        store = store_req

        adjust_qty = _parse_float(adj_raw)
        if adjust_qty is None or abs(adjust_qty) < 1e-09:
            field_errors['adjust_qty'] = 'AdjustQty is required (non-zero).'
            adjust_qty = 0.0

        factor = _uom_factor(item_code, uom) if item_code > 0 else 1.0
        base_qty = float(adjust_qty) * factor
        new_qty = float(current_qty) + float(adjust_qty)
        lot_id: Optional[str] = None
        if lot_raw is not None and str(lot_raw).strip():
            lot_id = str(lot_raw).strip()

        line: Dict[str, Any] = {
            'item_code': item_code,
            'item_name': item_name,
            'uom': uom,
            'store': store,
            'current_qty': current_qty,
            'adjust_qty': adjust_qty,
            'new_qty': new_qty,
            'base_qty': base_qty,
            'cost': cost,
            'sheet_row': sheet_row,
        }
        if lot_id:
            line['lot_id'] = lot_id
        if field_errors:
            line['field_errors'] = field_errors
            errors.append(f'Row {sheet_row}: ' + '; '.join(field_errors.values()))
        lines.append(line)
    return lines, errors
