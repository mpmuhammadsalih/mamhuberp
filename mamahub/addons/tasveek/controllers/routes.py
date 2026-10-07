"""Tasveek: TBLONLINEDATA from HO (multi-DB) or default business connection (single DB)."""
from __future__ import annotations
import csv
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
import requests
from nexa_http import Blueprint, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename
from config.settings import is_multi_db_mode
from db import _detect_column, _detect_table, _get_connection, _get_tenant_connection, _materialize_db_value
_ADDON_ROOT = Path(__file__).resolve().parents[1]
TABLE_CANDIDATES = ['TBLONLINEDATA', 'tblonlinedata', 'TblOnlineData']
MAX_ROWS = 2000
MAX_IMPORT_ROWS = 5000
ROWID_HEX_COL = 'TV_ROWID_HEX'
RFSR_COLUMN = 'RFSR'
TASVEEK_RAWABI_WHOLESALE_API = os.environ.get('TASVEEK_RAWABI_WHOLESALE_API', 'https://tasveekapi.rgcdynamics.store/rawabiwholesaledata')
RAWABI_API_COLUMN_ORDER = ('Store_No', 'Barcode', 'Product_Name', 'Sales_Price', 'Stock', 'System stock', 'ItemNo', 'Uom', 'ItemStatus', 'Offer_Price', 'Price_Change')
SYSTEM_STOCK_COL = 'System stock'

def _normalize_rawabi_api_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        out: List[Dict[str, Any]] = []
        for x in payload:
            if isinstance(x, dict):
                out.append(x)
        return out
    if isinstance(payload, dict):
        inner = payload.get('data') or payload.get('items') or payload.get('results') or payload.get('records') or payload.get('rows') or payload.get('Rows') or payload.get('list') or payload.get('content')
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []

def _rawabi_columns_for_rows(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return list(RAWABI_API_COLUMN_ORDER)
    seen = set()
    ordered: List[str] = []
    for key in RAWABI_API_COLUMN_ORDER:
        if any((key in r for r in rows)):
            ordered.append(key)
            seen.add(key)
    for r in rows[:5]:
        for k in sorted(r.keys()):
            if k not in seen:
                ordered.append(str(k))
                seen.add(str(k))
    return ordered

def _filter_rawabi_rows(rows: List[Dict[str, Any]], q: str) -> List[Dict[str, Any]]:
    """Case-insensitive substring match against any JSON value."""
    qs = (q or '').strip()
    if not qs:
        return list(rows)
    qu = qs.upper()
    out: List[Dict[str, Any]] = []
    for r in rows:
        matched = False
        for v in r.values():
            if v is None:
                continue
            if qu in str(v).upper():
                matched = True
                break
        if matched:
            out.append(r)
    return out

def _tasveek_normalize_api_scalar(val: Any) -> str:
    if val is None:
        return ''
    if isinstance(val, float):
        try:
            if val == int(val):
                return str(int(val))
        except (TypeError, ValueError):
            pass
    return str(val).strip()

def _tasveek_api_rawabi_and_uom(row: Dict[str, Any]) -> Tuple[str, str]:
    """Raw ABI code from ItemNo (preferred) or Barcode; unit from Uom — aligned with ITEMMASTERDETAILS."""
    item_no = row.get('ItemNo')
    if item_no is None:
        for k in ('itemNo', 'itemno', 'ITEMNO'):
            if k in row:
                item_no = row[k]
                break
    barcode = row.get('Barcode')
    if barcode is None:
        barcode = row.get('barcode')
    ra_raw = item_no if item_no not in (None, '') else barcode
    ra = _tasveek_normalize_api_scalar(ra_raw)
    uom = row.get('Uom')
    if uom is None:
        for k in ('UOM', 'uom'):
            if k in row:
                uom = row[k]
                break
    u_norm = _tasveek_normalize_api_scalar(uom).upper()
    return (ra, u_norm)

def _tasveek_merge_system_stock_column(cols: List[str]) -> List[str]:
    if SYSTEM_STOCK_COL in cols:
        return cols
    out = list(cols)
    anchor = 'Stock'
    if anchor in out:
        out.insert(out.index(anchor) + 1, SYSTEM_STOCK_COL)
    else:
        out.append(SYSTEM_STOCK_COL)
    return out

def _tasveek_fetch_system_stock_map(pairs: List[Tuple[str, str]]) -> Dict[Tuple[str, str], float]:
    """SUM(currentstock) from ITEMMASTERDETAILS (all TABLE rows), keyed by (trim(rawabicode), upper(trim(unit)))."""
    seen: Set[Tuple[str, str]] = set()
    uniq: List[Tuple[str, str]] = []
    for ra, uu in pairs:
        ra_s = (ra or '').strip()
        if not ra_s:
            continue
        u_s = (uu or '').strip().upper()
        key = (ra_s, u_s)
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    if not uniq:
        return {}
    imd_tbl = _detect_table(['ITEMMASTERDETAILS', 'itemmasterdetails']) or 'itemmasterdetails'
    rab = _detect_column(imd_tbl, ['RAWABICODE', 'rawabicode'])
    unt = _detect_column(imd_tbl, ['UNIT', 'unit'])
    stk = _detect_column(imd_tbl, ['CURRENTSTOCK', 'currentstock'])
    if not (rab and unt and stk):
        return {}
    out_map: Dict[Tuple[str, str], float] = {}
    chunk_size = 80
    try:
        with _get_connection() as conn:
            for start in range(0, len(uniq), chunk_size):
                chunk = uniq[start:start + chunk_size]
                or_parts: List[str] = []
                params: Dict[str, Any] = {}
                for idx, (ra_val, u_val) in enumerate(chunk):
                    or_parts.append(f"(TRIM(TO_CHAR(i.{rab})) = :ra{idx} AND UPPER(TRIM(NVL(i.{unt}, ''))) = :uu{idx})")
                    params[f'ra{idx}'] = ra_val
                    params[f'uu{idx}'] = u_val
                sql = f"\n                    SELECT TRIM(TO_CHAR(i.{rab})) AS ra_k,\n                           UPPER(TRIM(NVL(i.{unt}, ''))) AS u_k,\n                           SUM(NVL(i.{stk}, 0)) AS sqty\n                    FROM {imd_tbl} i\n                    WHERE ({' OR '.join(or_parts)})\n                    GROUP BY TRIM(TO_CHAR(i.{rab})), UPPER(TRIM(NVL(i.{unt}, '')))\n                "
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    for row in cur.fetchall() or []:
                        ra_k = _tasveek_normalize_api_scalar(row[0])
                        u_k = _tasveek_normalize_api_scalar(row[1]).upper()
                        qty_raw = row[2] if len(row) > 2 else 0
                        qty_v = _materialize_db_value(qty_raw)
                        try:
                            qty = float(qty_v) if qty_v is not None else 0.0
                        except (TypeError, ValueError):
                            qty = 0.0
                        out_map[ra_k, u_k] = qty
    except Exception:
        return {}
    return out_map

def _tasveek_attach_system_stock(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    pairs = [_tasveek_api_rawabi_and_uom(r) for r in rows]
    stock_map = _tasveek_fetch_system_stock_map(pairs)
    out: List[Dict[str, Any]] = []
    for r, (ra, uu) in zip(rows, pairs):
        rd = dict(r)
        ra_s = ra.strip()
        key = (ra_s, uu.strip().upper())
        if not ra_s:
            rd[SYSTEM_STOCK_COL] = ''
        elif key in stock_map:
            rd[SYSTEM_STOCK_COL] = stock_map[key]
        else:
            rd[SYSTEM_STOCK_COL] = 0
        out.append(rd)
    return out

def _tasveek_parse_api_qty(val: Any) -> Optional[float]:
    """Parse API Stock / System stock cell for numeric comparison."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(',', '')
    if s == '':
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None

def _tasveek_row_stock_variance(row: Dict[str, Any]) -> bool:
    """True when API Stock and System stock are both numeric and differ (beyond float tolerance)."""
    api_q = _tasveek_parse_api_qty(row.get('Stock'))
    sys_q = _tasveek_parse_api_qty(row.get(SYSTEM_STOCK_COL))
    if api_q is None or sys_q is None:
        return False
    return abs(api_q - sys_q) > 1e-06

def _tasveek_row_stock_aligned(row: Dict[str, Any]) -> bool:
    """Both sides numeric and equal."""
    api_q = _tasveek_parse_api_qty(row.get('Stock'))
    sys_q = _tasveek_parse_api_qty(row.get(SYSTEM_STOCK_COL))
    if api_q is None or sys_q is None:
        return False
    return abs(api_q - sys_q) <= 1e-06

def _tasveek_normalize_variance_filter(raw: Optional[str]) -> str:
    k = (raw or '').strip().lower()
    if k in ('diff', 'variance', 'mismatch', 'mismatched'):
        return 'diff'
    if k in ('match', 'aligned', 'ok', 'same'):
        return 'match'
    return 'all'

def _tasveek_apply_variance_filter(rows: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    mode_n = _tasveek_normalize_variance_filter(mode)
    if mode_n == 'diff':
        return [r for r in rows if _tasveek_row_stock_variance(r)]
    if mode_n == 'match':
        return [r for r in rows if _tasveek_row_stock_aligned(r)]
    return list(rows)

def _tasveek_tag_variance_rows(rows: List[Dict[str, Any]]) -> None:
    """Set internal flag for template row styling (not exported as a column)."""
    for r in rows:
        r['_tap_stock_variance'] = bool(_tasveek_row_stock_variance(r))
_ITEMSTATUS_ROW_KEYS = ('ItemStatus', 'itemStatus', 'ITEMSTATUS', 'ITEM_STATUS', 'item_status')

def _tasveek_row_item_status_raw(row: Dict[str, Any]) -> Any:
    for k in _ITEMSTATUS_ROW_KEYS:
        if k not in row:
            continue
        v = row[k]
        if v is None:
            continue
        if isinstance(v, str) and (not v.strip()):
            continue
        return v
    return None

def _tasveek_row_item_status_binary(row: Dict[str, Any]) -> Optional[str]:
    """Normalize ItemStatus to '1' or '0' when recognizable; else None."""
    v = _tasveek_row_item_status_raw(row)
    if v is None:
        return None
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, (int, float)):
        if v == 1:
            return '1'
        if v == 0:
            return '0'
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if s == '1':
        return '1'
    if s == '0':
        return '0'
    if s in ('true', 'yes', 'y', 'active', 'on', 'enabled', 't'):
        return '1'
    if s in ('false', 'no', 'n', 'inactive', 'off', 'disabled', 'f'):
        return '0'
    try:
        n = float(s.replace(',', ''))
        if n == 1.0:
            return '1'
        if n == 0.0:
            return '0'
    except (TypeError, ValueError):
        pass
    return None

def _tasveek_normalize_item_status_filter(sel: Optional[str]) -> str:
    s = (sel or '').strip()
    return s if s in ('1', '0') else ''

def _tasveek_filter_item_status(rows: List[Dict[str, Any]], sel: Optional[str]) -> List[Dict[str, Any]]:
    """Filter by ItemStatus bucket 1 or 0; empty sel keeps all rows."""
    want = _tasveek_normalize_item_status_filter(sel)
    if not want:
        return list(rows)
    return [r for r in rows if _tasveek_row_item_status_binary(r) == want]

def _tasveek_rawabi_empty_hint(*, api_row_total: int, after_search: int, after_item_status: int, search_q: str, item_status: str, stock_variance: str) -> Optional[str]:
    """Explain why the grid is empty (no upstream HTTP error)."""
    sv = _tasveek_normalize_variance_filter(stock_variance)
    if api_row_total == 0:
        return 'The upstream Rawabi API returned no rows for this page. Try page 1, increase per page, or confirm the API URL / service.'
    sq = (search_q or '').strip()
    if after_search == 0 and sq:
        return 'Search removed every row on this API page. Clear search or try different keywords (substring match on any column).'
    if after_item_status == 0 and item_status in ('1', '0') and (after_search > 0):
        return 'Item status removed every row on this page. Values may not map to 0/1 (we also treat common synonyms such as true/false, yes/no, active/inactive). Choose «All» or inspect ItemStatus on the grid without this filter.'
    if sv == 'diff' and after_item_status > 0:
        return 'Mismatch only keeps rows where both Stock and System stock are numeric but different — none matched. Try «All rows» or check that system stock exists.'
    if sv == 'match' and after_item_status > 0:
        return 'Match only keeps rows where both Stock and System stock are numeric and equal — none matched. Try «All rows».'
    return 'No rows left after filters on this API page. Relax filters or try another page.'

def _load_rawabi_api_page(page: int, per_page: int, search_q: str) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], bool, int]:
    """Fetch one Rawabi API page, apply client-side filter. Returns filtered rows, columns, error, has_more, api_row_total."""
    rows_loaded: List[Dict[str, Any]] = []
    err_msg: Optional[str] = None
    try:
        resp = requests.get(TASVEEK_RAWABI_WHOLESALE_API, params={'page': page, 'per_page': per_page}, timeout=90, headers={'Accept': 'application/json, text/plain;q=0.9'})
        resp.raise_for_status()
        rows_loaded = _normalize_rawabi_api_payload(resp.json())
    except requests.exceptions.RequestException as e:
        err_msg = str(e) or 'Request failed.'
    except Exception as e:
        err_msg = 'Could not read or parse API response: {}'.format(e)
    filtered_rows = _filter_rawabi_rows(rows_loaded, search_q)
    cols = _rawabi_columns_for_rows(filtered_rows)
    has_more = bool(rows_loaded) and len(rows_loaded) >= per_page
    return (filtered_rows, cols, err_msg, has_more, len(rows_loaded))

def _dict_rows_to_xlsx_bytes(columns: List[str], rows: List[Dict[str, Any]]) -> io.BytesIO:
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise RuntimeError('Excel export requires openpyxl (pip install openpyxl).') from e
    wb = Workbook()
    ws = wb.active
    for j, col in enumerate(columns, 1):
        ws.cell(row=1, column=j, value=col)
    for i, rd in enumerate(rows, 2):
        for j, col in enumerate(columns, 1):
            v = rd.get(col)
            if v is not None and hasattr(v, 'read'):
                try:
                    v = v.read()
                except Exception:
                    v = str(v)
            ws.cell(row=i, column=j, value=v if v is not None else '')
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio
_PRODUCT_SEARCH_COLS_ORDER = ('RAWABICODE', 'ITEMCODE', 'BARCODE', 'PRODUCTCODE', 'PRODUCT_CODE', 'ITEMNAME', 'PRODUCTNAME', 'DESCRIPTION')
_LEGACY_TBLONLINE_IMPORT_HEADERS: Dict[str, str] = {'MANUFACTURRID': 'BARCODE', 'RFSRSTATUS': 'RFSR'}
_TASVEEK_IMPORT_DEDUPE_KEY_PREFERRED: Tuple[str, ...] = ('RAWABICODE', 'BARCODE')

def _tasveek_import_key_columns(import_cols: List[str]) -> List[str]:
    """Columns used to detect duplicates (file + DB). Subset of import_cols; may be empty."""
    up = [str(c).upper() for c in import_cols]
    have = {up[i]: import_cols[i] for i in range(len(import_cols))}
    out: List[str] = []
    for want in _TASVEEK_IMPORT_DEDUPE_KEY_PREFERRED:
        if want in have and have[want] not in out:
            out.append(have[want])
    if len(out) >= 1:
        return out
    return []

def _materialize_import_rows(row_iterable: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(r) for r in row_iterable]

def _import_row_dedupe_fingerprint(row: Dict[str, Any], key_cols: List[str], import_cols: List[str], value_for: Callable[..., Any]) -> Tuple[Any, ...]:
    """Stable tuple for deduplication; empty keys fall back to full-row fingerprint."""
    if key_cols:
        parts: List[str] = []
        any_val = False
        for kc in key_cols:
            v = value_for(kc, row)
            s = str(v).strip() if v is not None else ''
            if s:
                any_val = True
            parts.append(s.lower())
        if any_val:
            return ('K',) + tuple(parts)
    tup = []
    for c in import_cols:
        v = value_for(c, row)
        tup.append(str(v).strip().lower() if v is not None else '')
    return ('F',) + tuple(tup)

def _dedupe_import_rows_last_wins(rows: List[Dict[str, Any]], key_cols: List[str], import_cols: List[str], value_for: Callable[..., Any]) -> List[Dict[str, Any]]:
    """Remove duplicate rows in the file (same key → keep last row)."""
    out_map: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for r in rows:
        fp = _import_row_dedupe_fingerprint(r, key_cols, import_cols, value_for)
        out_map[fp] = r
    return list(out_map.values())

def _key_values_for_db_delete(row: Dict[str, Any], key_cols: List[str], value_for: Callable[..., Any]) -> Optional[List[str]]:
    """Return list of non-empty string values for DELETE … AND …, or None if unsafe to delete."""
    out: List[str] = []
    for kc in key_cols:
        v = value_for(kc, row)
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        out.append(s)
    return out

def _tasveek_conn():
    """Prefer HO tenant DB (head office online data); fallback to session default."""
    if is_multi_db_mode():
        try:
            return _get_tenant_connection('HO')
        except Exception:
            pass
    return _get_connection()

def _table_exists(conn, table_upper: str) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = UPPER(:t)', {'t': table_upper})
        row = cur.fetchone()
        return bool(row and row[0])

def _resolve_table(conn) -> Optional[str]:
    for name in TABLE_CANDIDATES:
        if _table_exists(conn, name.upper()):
            return name
    return None

def _table_columns_ordered(conn, tbl: str) -> List[str]:
    t = tbl.upper().replace('"', '').split('.')[-1]
    with conn.cursor() as cur:
        cur.execute('\n            SELECT column_name\n            FROM user_tab_columns\n            WHERE table_name = :t\n            ORDER BY column_id\n            ', {'t': t})
        rows = cur.fetchall() or []
    return [str(r[0]).upper() for r in rows]

def _product_search_targets(cols: List[str]) -> List[str]:
    """Columns to search for the product filter (must exist on the table)."""
    want = {name: i for i, name in enumerate(_PRODUCT_SEARCH_COLS_ORDER)}
    found: List[Tuple[int, str]] = []
    seen: set = set()
    for c in cols:
        cu = str(c).upper()
        if cu in want and cu not in seen:
            seen.add(cu)
            found.append((want[cu], cu))
    found.sort(key=lambda x: x[0])
    return [name for _, name in found]

def _tasveek_columns_display_order(cols: List[str]) -> List[str]:
    """Match business layout: BARCODE immediately follows RAWABICODE when both exist (Oracle column_id otherwise)."""
    if not cols:
        return cols
    up = [str(c).upper() for c in cols]
    if 'BARCODE' not in up or 'RAWABICODE' not in up:
        return list(cols)
    no_barcode = [cols[i] for i, cu in enumerate(up) if cu != 'BARCODE']
    out: List[str] = []
    for c in no_barcode:
        out.append(c)
        if str(c).upper() == 'RAWABICODE':
            out.append('BARCODE')
    return out

def _rfsr_value_is_on(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, (int, float)):
        try:
            return float(raw) != 0.0
        except (TypeError, ValueError):
            return False
    s = str(raw).strip().upper()
    if not s:
        return False
    return s in ('1', 'Y', 'YES', 'T', 'TRUE', 'ON')

def _rfsr_meta(conn, tbl: str) -> Optional[str]:
    """DATA_TYPE for RFSR column, or None if column missing."""
    t = tbl.upper().replace('"', '').split('.')[-1]
    with conn.cursor() as cur:
        cur.execute('\n            SELECT data_type\n            FROM user_tab_columns\n            WHERE table_name = :t AND column_name = :c\n            ', {'t': t, 'c': RFSR_COLUMN})
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0] or '').upper()

def _rfsr_flipped_value(current: Any, data_type: str) -> Any:
    on = _rfsr_value_is_on(current)
    dt = (data_type or '').upper()
    if dt == 'NUMBER':
        return 1 if not on else 0
    return 'Y' if not on else 'N'

def _rows_to_display(conn, tbl: str, limit: int, product_q: Optional[str]=None) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = _tasveek_columns_display_order(_table_columns_ordered(conn, tbl))
    if not cols:
        return ([], [])
    search_cols = _product_search_targets(cols)
    pq = (product_q or '').strip()[:200]
    sel_parts: List[str] = []
    sel_parts.append('ROWID AS ' + ROWID_HEX_COL)
    sel_parts.extend(cols)
    col_sql = ', '.join(sel_parts)
    lim = max(1, min(limit, MAX_ROWS))
    params: Dict[str, Any] = {'lim': lim}
    if pq and search_cols:
        or_clauses = []
        for t in search_cols:
            or_clauses.append('(INSTR(UPPER(NVL(TO_CHAR(' + t + "), '')), UPPER(:pq)) > 0)")
        where_sql = '(' + ' OR '.join(or_clauses) + ')'
        params['pq'] = pq
        q = f'SELECT {col_sql} FROM {tbl} WHERE {where_sql} AND ROWNUM <= :lim'
    else:
        q = f'SELECT {col_sql} FROM {tbl} WHERE ROWNUM <= :lim'
    with conn.cursor() as cur:
        cur.execute(q, params)
        colnames = [str(d[0]).upper() for d in cur.description or []]
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall() or []:
            od = {colnames[i]: row[i] if i < len(row) else None for i in range(len(colnames))}
            for k, v in list(od.items()):
                if str(k).upper() == ROWID_HEX_COL and v is not None:
                    od[k] = str(v)
                elif hasattr(v, 'read'):
                    try:
                        od[k] = v.read()
                    except Exception:
                        od[k] = str(v)
            out.append(od)
        return (cols, out)
bp = Blueprint('tasveek', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'), url_prefix='/online')

@bp.route('/tasveek/rfsr-toggle', methods=['POST'])
def tasveek_rfsr_toggle():
    """Flip RFSR for one row addressed by ROWID (from list view). NUMBER → 1/0, else → Y/N."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Authentication required'}, 401)
    body = request.get_json(silent=True) or {}
    rid_hex = (body.get('rowid_hex') or '').strip()
    if not rid_hex:
        return jsonify({'ok': False, 'error': 'Missing row identifier'}, 400)
    conn = None
    try:
        conn = _tasveek_conn()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}, 503)
    try:
        tbl = _resolve_table(conn)
        if not tbl:
            return jsonify({'ok': False, 'error': 'TBLONLINEDATA not found'}, 404)
        dtypes = _table_columns_ordered(conn, tbl)
        if not dtypes or RFSR_COLUMN not in dtypes:
            return jsonify({'ok': False, 'error': 'RFSR column not found'}, 404)
        dt = _rfsr_meta(conn, tbl)
        if dt is None:
            return jsonify({'ok': False, 'error': 'RFSR column meta not found'}, 404)
        with conn.cursor() as cur:
            cur.execute('SELECT ' + RFSR_COLUMN + ' FROM ' + tbl + ' WHERE ROWID = CHARTOROWID(:r)', {'r': rid_hex})
            row_one = cur.fetchone()
            if not row_one:
                conn.rollback()
                return jsonify({'ok': False, 'error': 'Row not found'}, 404)
            current = row_one[0]
            new_val = _rfsr_flipped_value(current, dt)
            cur.execute('UPDATE ' + tbl + ' SET ' + RFSR_COLUMN + ' = :v WHERE ROWID = CHARTOROWID(:r)', {'v': new_val, 'r': rid_hex})
            if cur.rowcount < 1:
                conn.rollback()
                return jsonify({'ok': False, 'error': 'Row not found or not updated'}, 404)
        conn.commit()
        on = _rfsr_value_is_on(new_val)
        return jsonify({'ok': True, 'on': on, 'stored': new_val, 'display': str(new_val) if new_val is not None else ''})
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(e)}, 500)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@bp.route('/tasveek/delete-row', methods=['POST'])
def tasveek_delete_row():
    """DELETE one row from TBLONLINEDATA by ROWID."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Authentication required'}, 401)
    body = request.get_json(silent=True) or {}
    rid_hex = (body.get('rowid_hex') or '').strip()
    if not rid_hex:
        return jsonify({'ok': False, 'error': 'Missing row identifier'}, 400)
    conn = None
    try:
        conn = _tasveek_conn()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}, 503)
    try:
        tbl = _resolve_table(conn)
        if not tbl:
            return jsonify({'ok': False, 'error': 'TBLONLINEDATA not found'}, 404)
        with conn.cursor() as cur:
            cur.execute('DELETE FROM ' + tbl + ' WHERE ROWID = CHARTOROWID(:r)', {'r': rid_hex})
            if cur.rowcount < 1:
                conn.rollback()
                return jsonify({'ok': False, 'error': 'Row not found'}, 404)
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'error': str(e)}, 500)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def _norm_header(h: str) -> str:
    return (h or '').strip().upper().replace(' ', '_').replace('-', '_')

def _parse_xlsx_to_headers_and_rows(raw: bytes) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
    """Row 1 = headers. Rows 2+ are data; capped at MAX_IMPORT_ROWS."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], [], 'Excel requires openpyxl (pip install openpyxl)')
    bio = io.BytesIO(raw)
    wb = load_workbook(bio, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_it = ws.iter_rows(values_only=True)
        first = next(rows_it, None)
        if first is None:
            return ([], [], 'Excel file has no rows.')
        headers: List[str] = []
        for c in first:
            if c is None:
                headers.append('')
            else:
                s = str(c).strip()
                headers.append(s if s else '')
        out_rows: List[Dict[str, Any]] = []
        for row in rows_it:
            if len(out_rows) >= MAX_IMPORT_ROWS:
                break
            rd: Dict[str, Any] = {}
            for i, h in enumerate(headers):
                if not h:
                    continue
                v = row[i] if i < len(row) else None
                rd[h] = v
            out_rows.append(rd)
        return (headers, out_rows, None)
    finally:
        try:
            wb.close()
        except Exception:
            pass

def _import_tblonlinedata_rows(conn, tbl: str, cols_all: List[str], fieldnames_raw: Optional[List[str]], row_iterable: Iterable[Dict[str, Any]]) -> Tuple[int, int, int, int, Optional[str], List[str]]:
    """INSERT rows matched by header names.

    - Deduplicates rows in the file (same key → last wins).
    - When RAWABICODE and/or BARCODE are mapped, deletes existing rows with the same key
      before INSERT so re-imports replace instead of accumulating duplicates.

    Returns (inserted, skipped, deleted_existing, file_duplicate_rows_removed, error_message,
             skip_error_samples) — last is up to 5 distinct DB error strings when rows are skipped.
    """
    if not fieldnames_raw:
        return (0, 0, 0, 0, 'File has no header row.', [])
    header_to_srckey: Dict[str, str] = {}
    for fn in fieldnames_raw:
        nk = _norm_header(fn or '')
        if nk and nk not in header_to_srckey:
            header_to_srckey[nk] = fn if fn else ''
    cols_set = frozenset((c.upper() for c in cols_all))
    for old_hdr, oracle_col in _LEGACY_TBLONLINE_IMPORT_HEADERS.items():
        ou = oracle_col.upper()
        if ou in cols_set and old_hdr in header_to_srckey and (ou not in header_to_srckey):
            header_to_srckey[ou] = header_to_srckey[old_hdr]
    import_cols = [c for c in cols_all if c.upper() in header_to_srckey]
    if not import_cols:
        return (0, 0, 0, 0, 'No column matches {}. Headers must match Oracle column names (use Download format from this page).'.format(tbl), [])
    key_cols = _tasveek_import_key_columns(import_cols)
    rows_raw = _materialize_import_rows(row_iterable)
    rows_all = rows_raw[:MAX_IMPORT_ROWS]

    def _value_for(col: str, rd: Dict[str, Any]) -> Any:
        nk = col.upper()
        src_key = header_to_srckey.get(nk)
        if src_key is None:
            return None
        raw_v = rd.get(src_key)
        if raw_v is None:
            return None
        s = str(raw_v).strip()
        return None if s == '' else s
    rows_deduped = _dedupe_import_rows_last_wins(rows_all, key_cols, import_cols, _value_for)
    file_dup_removed = len(rows_all) - len(rows_deduped)
    bind_parts = ','.join((':p' + str(i) for i in range(len(import_cols))))
    sql_insert = 'INSERT INTO ' + tbl + ' (' + ', '.join(import_cols) + ') VALUES (' + bind_parts + ')'
    inserted = 0
    skipped = 0
    deleted_existing = 0
    skip_err_seen: Set[str] = set()
    skip_err_samples: List[str] = []
    with conn.cursor() as cur:
        for row in rows_deduped:
            params_bind: Dict[str, Any] = {}
            for i, cn in enumerate(import_cols):
                params_bind['p' + str(i)] = _value_for(cn, row)
            kv = _key_values_for_db_delete(row, key_cols, _value_for) if key_cols else None
            try:
                cur.execute('SAVEPOINT tasveek_imp_row')
                del_this = 0
                if kv is not None and len(kv) == len(key_cols):
                    wheres = [kc + ' = :dk' + str(j) for j, kc in enumerate(key_cols)]
                    bind_del = {'dk' + str(j): kv[j] for j in range(len(key_cols))}
                    sql_del = 'DELETE FROM ' + tbl + ' WHERE ' + ' AND '.join(wheres)
                    cur.execute(sql_del, bind_del)
                    rc = getattr(cur, 'rowcount', None)
                    if rc is not None and rc > 0:
                        del_this = int(rc)
                cur.execute(sql_insert, params_bind)
                inserted += 1
                deleted_existing += del_this
            except Exception as e:
                try:
                    cur.execute('ROLLBACK TO SAVEPOINT tasveek_imp_row')
                except Exception:
                    pass
                skipped += 1
                es = str(e).strip() or type(e).__name__
                if es not in skip_err_seen and len(skip_err_samples) < 5:
                    skip_err_seen.add(es)
                    skip_err_samples.append(es)
    conn.commit()
    return (inserted, skipped, deleted_existing, file_dup_removed, None, skip_err_samples)

def _positive_int_query(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int((request.args.get(name, str(default)) or '').strip())
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default

@bp.route('/tasveek/api-rawabi-data')
def tasveek_api_rawabi_data():
    """Rawabi wholesale data from tasveekapi.rgcdynamics.store (HTTPS). Pagination: page, per_page; search: q (filters current page)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    page = _positive_int_query('page', 1, 1, 100000)
    per_page = _positive_int_query('per_page', 100, 1, 500)
    search_q = (request.args.get('q') or request.args.get('search') or '').strip()[:200]
    stock_variance = _tasveek_normalize_variance_filter(request.args.get('stock_variance'))
    item_status = _tasveek_normalize_item_status_filter((request.args.get('item_status') or '').strip()[:10])
    filtered_rows, cols, err_msg, has_more, api_row_total = _load_rawabi_api_page(page, per_page, search_q)
    after_search = len(filtered_rows)
    filtered_rows = _tasveek_filter_item_status(filtered_rows, item_status)
    after_item_status = len(filtered_rows)
    filtered_rows = _tasveek_attach_system_stock(filtered_rows)
    _tasveek_tag_variance_rows(filtered_rows)
    filtered_rows = _tasveek_apply_variance_filter(filtered_rows, stock_variance)
    cols = _tasveek_merge_system_stock_column(list(cols))
    rawabi_empty_hint: Optional[str] = None
    if not err_msg and (not filtered_rows):
        rawabi_empty_hint = _tasveek_rawabi_empty_hint(api_row_total=api_row_total, after_search=after_search, after_item_status=after_item_status, search_q=search_q, item_status=item_status, stock_variance=stock_variance)
    return render_template('tasveek/tasveek_api_rawabi.html', columns=cols, rows=filtered_rows, error=err_msg, page=page, per_page=per_page, has_more=has_more, row_count=len(filtered_rows), api_row_total=api_row_total, search_q=search_q, stock_variance=stock_variance, item_status=item_status, rawabi_empty_hint=rawabi_empty_hint)

@bp.route('/tasveek/api-rawabi-data/export-xlsx')
def tasveek_api_rawabi_export_xlsx():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    page = _positive_int_query('page', 1, 1, 100000)
    per_page = _positive_int_query('per_page', 100, 1, 500)
    search_q = (request.args.get('q') or request.args.get('search') or '').strip()[:200]
    stock_variance = _tasveek_normalize_variance_filter(request.args.get('stock_variance'))
    item_status = _tasveek_normalize_item_status_filter((request.args.get('item_status') or '').strip()[:10])
    filtered_rows, cols, err_msg, _, _ = _load_rawabi_api_page(page, per_page, search_q)
    filtered_rows = _tasveek_filter_item_status(filtered_rows, item_status)
    filtered_rows = _tasveek_attach_system_stock(filtered_rows)
    _tasveek_tag_variance_rows(filtered_rows)
    filtered_rows = _tasveek_apply_variance_filter(filtered_rows, stock_variance)
    cols = _tasveek_merge_system_stock_column(list(cols))
    if err_msg:
        flash(err_msg, 'error')
        return redirect(url_for('tasveek.tasveek_api_rawabi_data', page=page, per_page=per_page, q=search_q or None, stock_variance=stock_variance if stock_variance != 'all' else None, item_status=item_status or None))
    if not cols and (not filtered_rows):
        cols = list(RAWABI_API_COLUMN_ORDER)
    try:
        bio = _dict_rows_to_xlsx_bytes(cols, filtered_rows)
    except RuntimeError as e:
        flash(str(e), 'error')
        return redirect(url_for('tasveek.tasveek_api_rawabi_data', page=page, per_page=per_page, q=search_q or None, stock_variance=stock_variance if stock_variance != 'all' else None, item_status=item_status or None))
    fn = 'tasveek_api_rawabi_p{:d}_{}.xlsx'.format(page, datetime.now().strftime('%Y%m%d_%H%M%S'))
    return send_file(bio, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=fn)

@bp.route('/tasveek')
def tasveek_list():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    err: Optional[str] = None
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    table_name = ''
    conn = None
    try:
        conn = _tasveek_conn()
    except Exception as e:
        return render_template('tasveek/tasveek.html', error=f'Database connection failed: {e}', columns=[], rows=[], table_name=None, row_count=0, product_search=(request.args.get('product') or '').strip()[:200], product_search_columns=[])
    try:
        tbl = _resolve_table(conn)
        table_name = tbl or ''
        if not tbl:
            err = "Table TBLONLINEDATA was not found in this database user's schema. Create or grant access to TBLONLINEDATA in the HO database (multi-DB) or ensure the single-DB user owns the table."
        else:
            product_q = (request.args.get('product') or '').strip()
            columns, rows = _rows_to_display(conn, tbl, MAX_ROWS, product_q=product_q)
    except Exception as e:
        err = str(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    product_cols: List[str] = []
    if columns:
        try:
            product_cols = _product_search_targets(columns)
        except Exception:
            product_cols = []
    product_arg = (request.args.get('product') or '').strip()[:200]
    return render_template('tasveek/tasveek.html', error=err, columns=columns, rows=rows, table_name=table_name or None, row_count=len(rows), product_search=product_arg, product_search_columns=product_cols)

@bp.route('/tasveek/export-xlsx')
def tasveek_export_xlsx():
    """Download current Tasveek grid (respects product search) as .xlsx."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    product_q = (request.args.get('product') or '').strip()[:200]
    conn = None
    try:
        conn = _tasveek_conn()
    except Exception as e:
        flash('Database connection failed: {}'.format(e), 'error')
        return redirect(url_for('tasveek.tasveek_list', product=product_q or None))
    try:
        tbl = _resolve_table(conn)
        if not tbl:
            flash('TBLONLINEDATA not found.', 'error')
            return redirect(url_for('tasveek.tasveek_list', product=product_q or None))
        columns, rows = _rows_to_display(conn, tbl, MAX_ROWS, product_q=product_q)
        try:
            bio = _dict_rows_to_xlsx_bytes(columns, rows)
        except RuntimeError as e:
            flash(str(e), 'error')
            return redirect(url_for('tasveek.tasveek_list', product=product_q or None))
        safe_tbl = secure_filename(str(tbl).replace(' ', '_')) or 'TBLONLINEDATA'
        fn = 'tasveek_{}_{}.xlsx'.format(safe_tbl, datetime.now().strftime('%Y%m%d_%H%M%S'))
        return send_file(bio, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=fn)
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('tasveek.tasveek_list', product=product_q or None))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@bp.route('/tasveek/template')
def tasveek_template():
    """Download .xlsx with row 1 = Oracle column names for TBLONLINEDATA + Format sheet."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    conn = None
    try:
        conn = _tasveek_conn()
    except Exception as e:
        flash(f'Connection failed: {e}', 'error')
        return redirect(url_for('tasveek.tasveek_list'))
    try:
        tbl = _resolve_table(conn)
        if not tbl:
            flash('TBLONLINEDATA not found.', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        cols_all = _tasveek_columns_display_order(_table_columns_ordered(conn, tbl))
        if not cols_all:
            flash('Could not read table columns.', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        try:
            from openpyxl import Workbook
        except ImportError:
            flash('Excel template requires openpyxl (pip install openpyxl).', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        wb = Workbook()
        data_ws = wb.active
        data_title = str(tbl)[:31] or 'Data'
        data_ws.title = data_title
        for i, name in enumerate(cols_all, start=1):
            data_ws.cell(row=1, column=i, value=name)
        fmt = wb.create_sheet('Format', 1)
        lines = ['Tasveek import format (TBLONLINEDATA)', '', '1) Use the first sheet; row 1 must list Oracle column names exactly as shown (from your database).', '2) Data starts on row 2. Leave cells blank for columns you do not want to set.', '3) You may omit optional columns by deleting those columns from row 1 — only listed columns are inserted.', '4) Save as .xlsx and use Upload & import on the Tasveek page.', '5) CSV is also supported: same header row, comma-separated, UTF-8.', '', '6) Column order in this template matches the Tasveek list: BARCODE follows RAWABICODE when both exist.', '', 'Max {:d} rows per import. Rows that break database rules are skipped and counted.'.format(MAX_IMPORT_ROWS)]
        for r, line in enumerate(lines, start=1):
            fmt.cell(row=r, column=1, value=line)
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        safe_tbl = secure_filename(str(tbl).replace(' ', '_')) or 'TBLONLINEDATA'
        filename = 'tasveek_{}_import_template.xlsx'.format(safe_tbl)
        return send_file(bio, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

@bp.route('/tasveek/import', methods=['POST'])
def tasveek_import():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    fobj = request.files.get('csv_file') or request.files.get('file')
    if not fobj or not getattr(fobj, 'filename', None):
        flash('Choose a CSV or Excel file to import.', 'error')
        return redirect(url_for('tasveek.tasveek_list'))
    fname = secure_filename(str(fobj.filename))
    allowed = ('.csv', '.txt', '.xlsx', '.xlsm')
    if fname and (not fname.lower().endswith(allowed)):
        flash('Please upload a .csv, .txt, .xlsx, or .xlsm file.', 'error')
        return redirect(url_for('tasveek.tasveek_list'))
    conn = None
    try:
        raw = fobj.read()
        fieldnames_raw: Optional[List[str]] = None
        row_iterable: Optional[Iterable[Dict[str, Any]]] = None
        lower = fname.lower() if fname else ''
        if lower.endswith(('.csv', '.txt')):
            text = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else str(raw)
            dict_reader = csv.DictReader(io.StringIO(text))
            fieldnames_raw = dict_reader.fieldnames
            row_iterable = dict_reader
        elif lower.endswith(('.xlsx', '.xlsm')):
            if not isinstance(raw, bytes):
                raw = bytes(raw) if raw else b''
            fieldnames_raw, rows_list, xerr = _parse_xlsx_to_headers_and_rows(raw)
            if xerr:
                flash(xerr, 'error')
                return redirect(url_for('tasveek.tasveek_list'))
            row_iterable = rows_list
        else:
            flash('Unsupported file type.', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
    except Exception as e:
        flash(f'Could not read file: {e}', 'error')
        return redirect(url_for('tasveek.tasveek_list'))
    try:
        conn = _tasveek_conn()
    except Exception as e:
        flash(f'Connection failed: {e}', 'error')
        return redirect(url_for('tasveek.tasveek_list'))
    try:
        tbl = _resolve_table(conn)
        if not tbl:
            flash('TBLONLINEDATA not found.', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        cols_all = _tasveek_columns_display_order(_table_columns_ordered(conn, tbl))
        if not cols_all:
            flash('Could not read table columns.', 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        inserted, skipped, deleted_existing, dup_in_file, msg, skip_samples = _import_tblonlinedata_rows(conn, tbl, cols_all, fieldnames_raw, row_iterable)
        if msg:
            flash(msg, 'error')
            return redirect(url_for('tasveek.tasveek_list'))
        parts_out = ['Imported {:d} row(s).'.format(inserted)]
        if deleted_existing > 0:
            parts_out.append('{:d} existing row(s) removed (same key) before insert.'.format(deleted_existing))
        if dup_in_file > 0:
            parts_out.append('{:d} duplicate row(s) in file skipped (same key keeps last).'.format(dup_in_file))
        if skipped:
            parts_out.append('{:d} row(s) skipped (error or constraint).'.format(skipped))
            if skip_samples:
                parts_out.append('Sample errors: ' + ' | '.join(skip_samples))
        flash(' '.join(parts_out), 'success' if inserted > 0 else 'error')
    except Exception as e:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        flash(f'Import failed: {e}', 'error')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return redirect(url_for('tasveek.tasveek_list'))
