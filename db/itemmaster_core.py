"""ITEMMASTER row persistence: HO explicit-tenant + branch session connection.

Loaded after most of ``db``; uses :class:`_DbAccess` to reach ``db`` helpers without
import cycles. Public functions are re-exported from ``db`` for backward compatibility.
"""
from __future__ import annotations
import logging
import re
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

class _DbAccess:
    __slots__ = ()

    def __getattr__(self, name: str):
        import db
        return getattr(db, name)
dbm = _DbAccess()
_ITEMMASTER_REMAP_SKIP_STOCK_COLUMNS = frozenset({'CURRENTSTOCK', 'CURRENT_STOCK', 'TRANSITSTOCK', 'TEMPCURRENTSTOCK', 'AVERAGECOST', 'LANDINGCOST'})
_ITEMMASTER_ACCOUNT_COLUMNS_READY = False
_ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY = False

def _itemmaster_remap_skip_inventory_column(col_name: str) -> bool:
    """Stock/qty and per-store columns kept local on branch DB during HO ITEMMASTER sync (not prices)."""
    c = (col_name or '').strip().upper()
    if not c:
        return False
    if c in _ITEMMASTER_REMAP_SKIP_STOCK_COLUMNS:
        return True
    if re.fullmatch('STORE\\d+', c):
        return True
    if re.fullmatch('TEMPSTORE\\d+', c):
        return True
    return False

def remap_itemmaster_to_tenant(item_codes: List[int], target_tenant_id: str, source_location_code: Optional[int]=None, source_tenant_id: str='HO', itemmaster_update_only: bool=False) -> Dict[str, Any]:
    """Copy/update ITEMMASTER rows from current tenant DB to selected tenant DB."""
    target_tid = (target_tenant_id or '').strip()
    source_tid = (source_tenant_id or 'HO').strip() or 'HO'
    cleaned_codes: List[int] = []
    for code in item_codes or []:
        try:
            item_int = int(code)
        except (TypeError, ValueError):
            continue
        if item_int > 0 and item_int not in cleaned_codes:
            cleaned_codes.append(item_int)
    if not cleaned_codes:
        raise ValueError('Select at least one valid item.')
    if not target_tid:
        raise ValueError('Target database is required.')
    if dbm.is_multi_db_mode() and source_tid == target_tid:
        raise ValueError('Source and target DB cannot be the same.')
    src_loc: Optional[int] = None
    if source_location_code is not None and str(source_location_code).strip() != '':
        try:
            src_loc = int(source_location_code)
        except (TypeError, ValueError):
            try:
                src_loc = int(float(str(source_location_code).strip()))
            except (TypeError, ValueError):
                src_loc = None
    if src_loc is None or src_loc <= 0:
        auth_src = dbm.get_tenant_locationcode_from_auth(source_tid)
        src_loc = auth_src if auth_src is not None and auth_src > 0 else 1
    ten_rows = dbm._safe_rows_auth('SELECT locationcode FROM tenant_databases WHERE tenant_id = :tid', {'tid': target_tid})
    if not ten_rows:
        raise ValueError('Target tenant not found.')
    tgt_loc_raw = ten_rows[0].get('locationcode')
    if tgt_loc_raw is None:
        raise ValueError(f"Tenant {target_tid!r} has no locationcode in tenant_databases. Set each tenant's locationcode before syncing items.")
    try:
        target_loc = int(tgt_loc_raw)
    except (TypeError, ValueError):
        try:
            target_loc = int(float(str(tgt_loc_raw).strip()))
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Invalid locationcode for tenant {target_tid!r}.') from exc
    if target_loc <= 0:
        raise ValueError(f'Invalid locationcode for tenant {target_tid!r} (must be > 0).')
    source_rows: List[Dict[str, Any]] = []
    source_cols: List[str] = []
    source_alt_rows: List[Dict[str, Any]] = []
    with dbm._get_tenant_connection(source_tid) as src_conn:
        with src_conn.cursor() as src_cur:
            src_cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
            src_item_cols = {str(r[0]).upper() for r in src_cur.fetchall() or []}
            if 'ITEMCODE' not in src_item_cols:
                raise ValueError('ITEMMASTER table not found in source DB.')
            params: Dict[str, Any] = {}
            if 'LOCATIONCODE' in src_item_cols:
                where_loc = 'LOCATIONCODE = :loc AND '
                params['loc'] = src_loc
            else:
                where_loc = ''
            in_parts = []
            for idx, code in enumerate(cleaned_codes):
                key = f'i{idx}'
                in_parts.append(f':{key}')
                params[key] = code
            q = f"SELECT * FROM ITEMMASTER WHERE {where_loc}ITEMCODE IN ({', '.join(in_parts)})"
            src_cur.execute(q, params)
            source_cols = [str(d[0]).upper() for d in src_cur.description or []]
            for row in src_cur.fetchall() or []:
                source_rows.append(dict(zip(source_cols, row)))
            try:
                alt_params = dict(params)
                src_cur.execute(f"\n                    SELECT LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                           CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                    FROM ITEMALTERNATEUOMMAP\n                    WHERE LOCATIONCODE = :loc\n                      AND ITEMCODE IN ({', '.join(in_parts)})\n                    ORDER BY ITEMCODE, SLNO\n                    ", alt_params)
                alt_cols = [str(d[0]).upper() for d in src_cur.description or []]
                for row in src_cur.fetchall() or []:
                    source_alt_rows.append(dict(zip(alt_cols, row)))
            except Exception:
                source_alt_rows = []
    found_codes = {int(r.get('ITEMCODE') or 0) for r in source_rows if r.get('ITEMCODE') is not None}
    missing_codes = [x for x in cleaned_codes if x not in found_codes]
    if not source_rows:
        raise ValueError('No matching source items found.')
    inserted = 0
    updated = 0
    alt_inserted = 0
    alt_updated = 0
    synced_item_codes = set()
    with dbm._get_tenant_connection(target_tid) as tgt_conn:
        with tgt_conn.cursor() as tgt_cur:
            tgt_cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
            tgt_cols = {str(r[0]).upper() for r in tgt_cur.fetchall() or []}
            if 'ITEMCODE' not in tgt_cols:
                raise ValueError('ITEMMASTER table not found in target DB.')
            common_cols = [c for c in source_cols if c in tgt_cols]
            if 'ITEMCODE' not in common_cols:
                raise ValueError('Target ITEMMASTER missing ITEMCODE.')
            has_tgt_loc = 'LOCATIONCODE' in tgt_cols
            if has_tgt_loc and 'LOCATIONCODE' not in common_cols:
                common_cols.append('LOCATIONCODE')
            updatable_cols = [c for c in common_cols if c not in ('ITEMCODE', 'LOCATIONCODE') and (not _itemmaster_remap_skip_inventory_column(c))]
            for src in source_rows:
                try:
                    item_code = int(src.get('ITEMCODE') or 0)
                except (TypeError, ValueError):
                    continue
                if item_code <= 0:
                    continue
                if has_tgt_loc:
                    tgt_cur.execute('SELECT COUNT(*) FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': target_loc, 'icode': item_code})
                else:
                    tgt_cur.execute('SELECT COUNT(*) FROM ITEMMASTER WHERE ITEMCODE = :icode', {'icode': item_code})
                exists = int((tgt_cur.fetchone() or [0])[0] or 0) > 0
                row_data = dict(src)
                if has_tgt_loc:
                    row_data['LOCATIONCODE'] = target_loc
                if exists:
                    if updatable_cols:
                        set_sql = ', '.join([f'{c} = :{c}' for c in updatable_cols])
                        params_upd = {c: row_data.get(c) for c in updatable_cols}
                        params_upd['icode'] = item_code
                        if has_tgt_loc:
                            params_upd['loc'] = target_loc
                            where_sql = 'LOCATIONCODE = :loc AND ITEMCODE = :icode'
                        else:
                            where_sql = 'ITEMCODE = :icode'
                        tgt_cur.execute(f'UPDATE ITEMMASTER SET {set_sql} WHERE {where_sql}', params_upd)
                    updated += 1
                    synced_item_codes.add(item_code)
                else:
                    if itemmaster_update_only:
                        continue
                    insert_cols = ['ITEMCODE'] + [c for c in common_cols if c != 'ITEMCODE']
                    insert_cols = [c for c in insert_cols if c in tgt_cols and (not _itemmaster_remap_skip_inventory_column(c))]
                    if has_tgt_loc and 'LOCATIONCODE' not in insert_cols:
                        insert_cols.insert(0, 'LOCATIONCODE')
                    bind_sql = ', '.join([f':{c}' for c in insert_cols])
                    params_ins = {c: row_data.get(c) for c in insert_cols}
                    tgt_cur.execute(f"INSERT INTO ITEMMASTER ({', '.join(insert_cols)}) VALUES ({bind_sql})", params_ins)
                    inserted += 1
                    synced_item_codes.add(item_code)
            if source_alt_rows:
                try:
                    tgt_cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMALTERNATEUOMMAP'")
                    has_alt_table = int((tgt_cur.fetchone() or [0])[0] or 0) > 0
                except Exception:
                    has_alt_table = False
                if has_alt_table:
                    for alt in source_alt_rows:
                        try:
                            item_code = int(alt.get('ITEMCODE') or 0)
                        except (TypeError, ValueError):
                            continue
                        if item_code <= 0:
                            continue
                        if itemmaster_update_only and item_code not in synced_item_codes:
                            continue
                        alt_uom = str(alt.get('ALTERNATEUOMCODE') or '').strip()
                        if not alt_uom:
                            continue
                        params_key = {'loc': target_loc, 'icode': item_code, 'uom': alt_uom}
                        tgt_cur.execute('\n                            SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                            WHERE LOCATIONCODE = :loc\n                              AND ITEMCODE = :icode\n                              AND ALTERNATEUOMCODE = :uom\n                            ', params_key)
                        existing = tgt_cur.fetchone()
                        if existing:
                            tgt_cur.execute('\n                                UPDATE ITEMALTERNATEUOMMAP\n                                SET MANUFACTURERID = :mid,\n                                    CONVERSIONFACTOR = :cf,\n                                    COSTPRICE = :cp,\n                                    WHOLESALEPRICE = :wp,\n                                    RETAILPRICE = :rp,\n                                    THIRDPRICE = :tp,\n                                    BRANCHPRICE = :bp\n                                WHERE LOCATIONCODE = :loc\n                                  AND ITEMCODE = :icode\n                                  AND ALTERNATEUOMCODE = :uom\n                                ', {'loc': target_loc, 'icode': item_code, 'uom': alt_uom, 'mid': alt.get('MANUFACTURERID'), 'cf': alt.get('CONVERSIONFACTOR') or 0, 'cp': alt.get('COSTPRICE') or 0, 'wp': alt.get('WHOLESALEPRICE') or 0, 'rp': alt.get('RETAILPRICE') or 0, 'tp': alt.get('THIRDPRICE') or 0, 'bp': alt.get('BRANCHPRICE') or 0})
                            alt_updated += 1
                            continue
                        tgt_cur.execute('SELECT NVL(MAX(SLNO), 0) + 1 FROM ITEMALTERNATEUOMMAP WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': target_loc, 'icode': item_code})
                        next_slno = int((tgt_cur.fetchone() or [1])[0] or 1)
                        tgt_cur.execute('\n                            INSERT INTO ITEMALTERNATEUOMMAP (\n                                LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                                CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                            ) VALUES (\n                                :loc, :slno, :icode, :uom, :mid,\n                                :cf, :cp, :wp, :rp, :tp, :bp\n                            )\n                            ', {'loc': target_loc, 'slno': next_slno, 'icode': item_code, 'uom': alt_uom, 'mid': alt.get('MANUFACTURERID'), 'cf': alt.get('CONVERSIONFACTOR') or 0, 'cp': alt.get('COSTPRICE') or 0, 'wp': alt.get('WHOLESALEPRICE') or 0, 'rp': alt.get('RETAILPRICE') or 0, 'tp': alt.get('THIRDPRICE') or 0, 'bp': alt.get('BRANCHPRICE') or 0})
                        alt_inserted += 1
        tgt_conn.commit()
    return {'inserted': inserted, 'updated': updated, 'processed': inserted + updated, 'missing_codes': missing_codes, 'target_locationcode': target_loc, 'alt_inserted': alt_inserted, 'alt_updated': alt_updated}

def get_itemmaster_list_from_tenant(tenant_id: str, search: Optional[str]=None, page: int=1, items_per_page: int=100, location_code: Optional[int]=None, sort_by: Optional[str]=None, sort_dir: Optional[str]=None) -> Tuple[List[Dict[str, Any]], int]:
    """List ITEMMASTER rows from a specific tenant DB (used by HO central listing)."""
    rows: List[Dict[str, Any]] = []
    total_count = 0
    if page < 1:
        page = 1
    if items_per_page < 1:
        items_per_page = 100
    with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
            cols = {str(r[0]).upper() for r in cur.fetchall() or []}
            if 'ITEMCODE' not in cols:
                return ([], 0)
            barcode_col = 'MANUFACTURERID' if 'MANUFACTURERID' in cols else 'BARCODE' if 'BARCODE' in cols else None
            rawabi_col = 'RAWABICODE' if 'RAWABICODE' in cols else None
            uom_col = 'BASEUOM' if 'BASEUOM' in cols else 'UNITOFMEASUREMENT' if 'UNITOFMEASUREMENT' in cols else 'UOM' if 'UOM' in cols else None
            cost_col = 'COSTPRICE' if 'COSTPRICE' in cols else None
            retail_col = 'RETAILPRICE' if 'RETAILPRICE' in cols else None
            stock_expr = _itemmaster_stock_qty_sql(cols)
            created_by_col = None
            for c in ('CREATEDBY', 'CREATED_BY', 'USERID', 'USERNAME'):
                if c in cols:
                    created_by_col = c
                    break
            created_date_col = None
            for c in ('CREATEDDATE', 'CREATIONDATE', 'CREATED_AT', 'CDATE'):
                if c in cols:
                    created_date_col = c
                    break
            has_loc_col = 'LOCATIONCODE' in cols
            where_parts = ['1=1']
            params: Dict[str, Any] = {}
            if search and str(search).strip():
                params['search_like'] = f'%{str(search).strip().upper()}%'
                code_expr = 'UPPER(TO_CHAR(ITEMCODE)) LIKE :search_like'
                name_expr = "UPPER(NVL(ITEMNAME, '')) LIKE :search_like" if 'ITEMNAME' in cols else '1=0'
                bc_expr = f"UPPER(NVL({barcode_col}, '')) LIKE :search_like" if barcode_col else '1=0'
                rawabi_expr = f'UPPER(TO_CHAR({rawabi_col})) LIKE :search_like' if rawabi_col else '1=0'
                where_parts.append(f'({code_expr} OR {name_expr} OR {bc_expr} OR {rawabi_expr})')
            if has_loc_col and location_code is not None:
                params['loc'] = int(location_code)
                where_parts.append('LOCATIONCODE = :loc')
            where_sql = ' AND '.join(where_parts)
            cur.execute(f'SELECT COUNT(*) FROM ITEMMASTER WHERE {where_sql}', params)
            total_count = int((cur.fetchone() or [0])[0] or 0)
            if total_count <= 0:
                return ([], 0)
            select_parts = [f'{rawabi_col} AS rawabicode' if rawabi_col else 'NULL AS rawabicode', 'ITEMCODE AS itemcode', f'{barcode_col} AS manufacturerid' if barcode_col else 'NULL AS manufacturerid', 'ITEMNAME AS itemname' if 'ITEMNAME' in cols else 'NULL AS itemname', f'{uom_col} AS unitofmeasurement' if uom_col else 'NULL AS unitofmeasurement', f'{cost_col} AS costprice' if cost_col else '0 AS costprice', f'{retail_col} AS retailprice' if retail_col else '0 AS retailprice', f'{stock_expr} AS currentstock', f'{created_by_col} AS createdby' if created_by_col else 'NULL AS createdby', f"TO_CHAR({created_date_col}, 'YYYY-MM-DD HH24:MI:SS') AS createddate" if created_date_col else 'NULL AS createddate']
            start_row = (page - 1) * items_per_page + 1
            end_row = page * items_per_page
            page_params = dict(params)
            page_params['start_row'] = start_row
            page_params['end_row'] = end_row
            sort_key = (sort_by or 'rawabicode').strip().lower()
            sort_direction = 'DESC' if str(sort_dir or 'desc').strip().lower() != 'asc' else 'ASC'
            sort_map = {'rawabicode': 'q.rawabicode', 'itemcode': 'q.itemcode', 'barcode': 'q.manufacturerid', 'itemname': 'q.itemname', 'uom': 'q.unitofmeasurement', 'cost': 'q.costprice', 'retail': 'q.retailprice', 'currentstock': 'q.currentstock', 'username': 'q.createdby', 'createddate': 'q.createddate'}
            order_expr = sort_map.get(sort_key, 'q.rawabicode')
            order_sql = f'{order_expr} {sort_direction} NULLS LAST, q.itemcode ASC'
            cur.execute(f"\n                SELECT * FROM (\n                    SELECT q.*, ROW_NUMBER() OVER (ORDER BY {order_sql}) AS rn\n                    FROM (\n                        SELECT {', '.join(select_parts)}\n                        FROM ITEMMASTER\n                        WHERE {where_sql}\n                    ) q\n                )\n                WHERE rn BETWEEN :start_row AND :end_row\n                ", page_params)
            desc = [d[0].lower() for d in cur.description or []]
            for r in cur.fetchall() or []:
                rec = dict(zip(desc, r))
                rec.pop('rn', None)
                rows.append(rec)
    return (rows, total_count)

def _itemmaster_stock_qty_sql(cols: Set[str], table_alias: Optional[str]=None) -> str:
    """SQL expression for total qty for ITEMMASTER column set (listing / detail)."""
    prefix = f'{table_alias}.' if table_alias else ''
    for name in ('CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK', 'QTYONHAND', 'ONHAND', 'TOTALSTOCK'):
        if name in cols:
            return f'NVL({prefix}{name}, 0)'
    store_cols = sorted([c for c in cols if re.fullmatch('STORE\\d+', c)], key=lambda x: int(x[5:]))
    if store_cols:
        return '(' + ' + '.join((f'NVL({prefix}{c}, 0)' for c in store_cols)) + ')'
    return '0'

def get_next_item_code_for_tenant(tenant_id: str, location_code: int) -> int:
    """Get next ITEMCODE from a specific tenant DB and location."""
    loc = int(location_code or 1)
    with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT NVL(MAX(ITEMCODE), 0) + 1 FROM ITEMMASTER WHERE LOCATIONCODE = :loc', {'loc': loc})
            row = cur.fetchone()
            return int((row[0] if row else 1) or 1)

def get_item_by_code_for_tenant(tenant_id: str, item_code: int, location_code: int) -> Optional[Dict[str, Any]]:
    """Get item details by item code from a specific tenant DB."""
    tid = (tenant_id or '').strip()
    loc = int(location_code or 1)
    icode = int(item_code)
    try:
        dv = dbm.try_get_itemmaster_detail_view_for_tenant(tid, icode, loc)
        if dv:
            row, _ = dv
            if row:
                try:
                    if int(row.get('itemcode')) == icode and int(row.get('locationcode')) == loc:
                        return row
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    with dbm._get_tenant_connection(tid) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
            im_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
            if 'ITEMCODE' not in im_cols or 'LOCATIONCODE' not in im_cols:
                return None
            cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :t', {'t': 'CATEGORY'})
            category_tbl = bool((cur.fetchone() or [0])[0])
            parts: List[str] = []
            simple_cols = ('ITEMCODE', 'LOCATIONCODE', 'RAWABICODE', 'ITEMNAME', 'MANUFACTURERID', 'BRANDCODE', 'SIZECODE', 'COLORCODE', 'BASEUOM', 'COSTPRICE', 'RETAILPRICE', 'WHOLESALEPRICE', 'THIRDPRICE', 'BRANCHPRICE', 'MAXIMUMLEVEL', 'REORDERLEVEL', 'DISCOUNTFLAG', 'COMPANYCODE', 'SUPCODE', 'MAINCATEGORY', 'REBATE', 'ITEMNAMEARA', 'DESCRIPTION', 'PROPERTY', 'ORIGIN', 'QUANTITYLIMIT', 'PACKING', 'MINISTRYFACTOR', 'MINISTRYUNIT', 'VATPERCENT', 'ITEMFLAG', 'OWNPRODUCT', 'STORE', 'IMAGE_PATH')
            for c in simple_cols:
                if c in im_cols:
                    parts.append(f'im.{c}')
            stock_sql = _itemmaster_stock_qty_sql(im_cols, table_alias='im')
            parts.append(f'{stock_sql} AS CURRENTSTOCK')
            acct_aliases = (('SALESACCOUNT', 'SALES_ACCOUNT'), ('PURCHASEACCOUNT', 'PURCHASE_ACCOUNT'), ('INVENTORYACCOUNT', 'INVENTORY_ACCOUNT'), ('COGSACCOUNT', 'COGS_ACCOUNT'))
            for col, alias in acct_aliases:
                if col in im_cols:
                    parts.append(f'im.{col} AS {alias}')
            if category_tbl and 'DEPARTMENTCODE' in im_cols:
                parts.append("NVL((SELECT CODE FROM CATEGORY WHERE CODE = im.DEPARTMENTCODE AND FLAG = 'D'), im.DEPARTMENTCODE) AS DEPARTMENTCODE")
            elif 'DEPARTMENTCODE' in im_cols:
                parts.append('im.DEPARTMENTCODE')
            if category_tbl and 'CATEGORYCODE' in im_cols:
                parts.append("NVL((SELECT CODE FROM CATEGORY WHERE CODE = im.CATEGORYCODE AND FLAG = 'C'), im.CATEGORYCODE) AS CATEGORYCODE")
            elif 'CATEGORYCODE' in im_cols:
                parts.append('im.CATEGORYCODE')
            sql = f"SELECT {', '.join(parts)} FROM ITEMMASTER im WHERE im.ITEMCODE = :item_code AND im.LOCATIONCODE = :location_code"
            cur.execute(sql, {'item_code': icode, 'location_code': loc})
            row = cur.fetchone()
            if not row:
                return None
            out_cols = [str(d[0]).lower() for d in cur.description or []]
            data = dict(zip(out_cols, row))
            data['itemnameara'] = dbm._fix_mojibake(data.get('itemnameara'))
            data['display_item_name'] = dbm._display_item_name_prefer_arabic(data.get('itemname'), data.get('itemnameara'))
            return data

def get_item_by_manufacturer_id_for_tenant(tenant_id: str, manufacturer_id: str, location_code: int) -> Optional[Dict[str, Any]]:
    """Get item by manufacturer id from specific tenant DB."""
    with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT ITEMCODE FROM ITEMMASTER WHERE MANUFACTURERID = :mid AND LOCATIONCODE = :loc', {'mid': (manufacturer_id or '').strip(), 'loc': int(location_code)})
            row = cur.fetchone()
            if not row:
                return None
            return get_item_by_code_for_tenant(tenant_id, int(row[0]), int(location_code))

def get_item_rawabicode_for_tenant(tenant_id: str, item_code: int, location_code: int) -> str:
    """Get RAWABICODE from ITEMMASTER for specific tenant/location/item."""
    try:
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT RAWABICODE FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': int(location_code), 'icode': int(item_code)})
                row = cur.fetchone()
                return str(row[0]).strip() if row and row[0] is not None else ''
    except Exception:
        return ''

def _serialize_oracle_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, date):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()
    return s[:10] if len(s) >= 10 else s or None

def _normalize_po_import_uom(u: Any) -> str:
    s = str(u or '').strip().upper()
    return s if s else 'NOS'

def _normalize_po_import_rawabi_str(v: Any) -> str:
    if v is None:
        return ''
    return str(v).strip()

def _lookup_itemcode_by_rawabicode_and_uom_current(location_code: int, rawabi: str, uom_n: str) -> Optional[int]:
    """Match ITEMMASTER by RAWABICODE + invoice UOM (BASEUOM or ITEMALTERNATEUOMMAP)."""
    rawabi = (rawabi or '').strip()
    if not rawabi:
        return None
    imx = dbm._detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not imx:
        return None
    icols = {str(c).upper() for c in dbm._get_table_columns(imx) or []}
    if 'RAWABICODE' not in icols:
        return None
    ic_col = dbm._detect_column(imx, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) or 'ITEMCODE'
    loc_col = dbm._detect_column(imx, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) or 'LOCATIONCODE'
    uom_parts: List[str] = []
    if 'BASEUOM' in icols:
        uom_parts.append('UPPER(TRIM(im.BASEUOM)) = :uom')
    alt_tbl = dbm._detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap', 'ITEM_ALTERNATE_UOM_MAP'])
    if alt_tbl and dbm._table_exists(alt_tbl):
        alt_ic = dbm._detect_column(alt_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
        alt_loc = dbm._detect_column(alt_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        alt_uom = dbm._detect_column(alt_tbl, ['ALTERNATEUOMCODE', 'ALTERNATE_UOM_CODE', 'alternateuomcode'])
        if alt_ic and alt_loc and alt_uom:
            uom_parts.append(f'EXISTS (\n                    SELECT 1 FROM {alt_tbl} alt\n                    WHERE alt.{alt_loc} = im.{loc_col}\n                      AND alt.{alt_ic} = im.{ic_col}\n                      AND UPPER(TRIM(alt.{alt_uom})) = :uom\n                )')
    if not uom_parts:
        return None
    uom_predicate = '(' + ' OR '.join(uom_parts) + ')'
    sql = f'\n        SELECT x.ITEMCODE FROM (\n            SELECT im.{ic_col} AS ITEMCODE\n            FROM {imx} im\n            WHERE im.{loc_col} = :loc\n              AND TRIM(TO_CHAR(im.RAWABICODE)) = TRIM(:rawabi)\n              AND {uom_predicate}\n            ORDER BY im.{ic_col}\n        ) x WHERE ROWNUM = 1\n    '
    try:
        rows = dbm._safe_rows(sql, {'loc': int(location_code), 'rawabi': rawabi, 'uom': uom_n})
        if not rows:
            return None
        ic = rows[0].get('itemcode')
        if ic is None:
            return None
        return int(float(ic))
    except Exception:
        return None

def _lookup_itemcode_by_rawabicode_only_current(location_code: int, rawabi: str) -> Optional[int]:
    """First ITEMMASTER row at location with this RAWABICODE (no UOM filter)."""
    rawabi = (rawabi or '').strip()
    if not rawabi:
        return None
    imx = dbm._detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not imx:
        return None
    icols = {str(c).upper() for c in dbm._get_table_columns(imx) or []}
    if 'RAWABICODE' not in icols:
        return None
    ic_col = dbm._detect_column(imx, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) or 'ITEMCODE'
    loc_col = dbm._detect_column(imx, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) or 'LOCATIONCODE'
    sql = f'\n        SELECT x.ITEMCODE FROM (\n            SELECT im.{ic_col} AS ITEMCODE\n            FROM {imx} im\n            WHERE im.{loc_col} = :loc\n              AND TRIM(TO_CHAR(im.RAWABICODE)) = TRIM(:rawabi)\n            ORDER BY im.{ic_col}\n        ) x WHERE ROWNUM = 1\n    '
    try:
        rows = dbm._safe_rows(sql, {'loc': int(location_code), 'rawabi': rawabi})
        if not rows:
            return None
        ic = rows[0].get('itemcode')
        if ic is None:
            return None
        return int(float(ic))
    except Exception:
        return None

def _po_import_itemname_english_only(item_row: Optional[Dict[str, Any]]) -> str:
    """ITEMNAME column only (no Arabic/display merge)."""
    if not item_row:
        return ''
    return str(item_row.get('itemname') or '').strip()

@contextmanager
def _po_import_source_connection(source_tenant_id: str) -> Iterator[Any]:
    """BILLHDR/BILLDTL source: tenant DB in multi-DB mode, else current single DB connection."""
    tid = (source_tenant_id or '').strip()
    if not tid:
        raise ValueError('Source tenant is required.')
    if dbm.is_multi_db_mode() and tid != '__current__':
        conn = dbm._get_tenant_connection(tid)
    else:
        conn = dbm._get_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass

def fetch_rawabicode_from_source_itemmaster(source_tenant_id: str, source_location_code: int, source_item_code: int) -> str:
    """RAWABICODE from source tenant ITEMMASTER for invoice line itemcode (for cross-tenant PO import)."""
    tid = (source_tenant_id or '').strip()
    try:
        ic = int(source_item_code)
    except (TypeError, ValueError):
        return ''
    if not tid or ic <= 0:
        return ''
    try:
        sloc = int(source_location_code)
    except (TypeError, ValueError):
        sloc = 0

    def _cols_src(cur: Any, table_u: str) -> Set[str]:
        cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': table_u.upper()})
        return {str(r[0]).upper() for r in cur.fetchall() or []}
    try:
        with _po_import_source_connection(tid) as conn:
            with conn.cursor() as cur:
                im_cols = _cols_src(cur, 'ITEMMASTER')
                if not im_cols or 'RAWABICODE' not in im_cols or 'ITEMCODE' not in im_cols:
                    return ''
                wh = ['ITEMCODE = :ic']
                params: Dict[str, Any] = {'ic': ic}
                if 'LOCATIONCODE' in im_cols and sloc:
                    wh.append('LOCATIONCODE = :loc')
                    params['loc'] = sloc
                cur.execute(f"\n                    SELECT RAWABICODE FROM (\n                        SELECT RAWABICODE FROM ITEMMASTER\n                        WHERE {' AND '.join(wh)}\n                        ORDER BY ITEMCODE\n                    )\n                    WHERE ROWNUM = 1\n                    ", params)
                row = cur.fetchone()
                if not row or row[0] is None:
                    return ''
                return _normalize_po_import_rawabi_str(dbm._materialize_db_value(row[0]))
    except Exception:
        return ''

def fetch_itemname_from_source_itemmaster(source_tenant_id: str, source_location_code: int, source_item_code: int) -> str:
    """ITEMNAME (English column) from source tenant ITEMMASTER for invoice line itemcode."""
    tid = (source_tenant_id or '').strip()
    try:
        ic = int(source_item_code)
    except (TypeError, ValueError):
        return ''
    if not tid or ic <= 0:
        return ''
    try:
        sloc = int(source_location_code)
    except (TypeError, ValueError):
        sloc = 0

    def _cols_src(cur: Any, table_u: str) -> Set[str]:
        cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': table_u.upper()})
        return {str(r[0]).upper() for r in cur.fetchall() or []}
    try:
        with _po_import_source_connection(tid) as conn:
            with conn.cursor() as cur:
                im_cols = _cols_src(cur, 'ITEMMASTER')
                if not im_cols or 'ITEMCODE' not in im_cols or 'ITEMNAME' not in im_cols:
                    return ''
                wh = ['ITEMCODE = :ic']
                params: Dict[str, Any] = {'ic': ic}
                if 'LOCATIONCODE' in im_cols and sloc:
                    wh.append('LOCATIONCODE = :loc')
                    params['loc'] = sloc
                cur.execute(f"\n                    SELECT ITEMNAME FROM (\n                        SELECT ITEMNAME FROM ITEMMASTER\n                        WHERE {' AND '.join(wh)}\n                        ORDER BY ITEMCODE\n                    )\n                    WHERE ROWNUM = 1\n                    ", params)
                row = cur.fetchone()
                if not row or row[0] is None:
                    return ''
                return str(dbm._materialize_db_value(row[0]) or '').strip()
    except Exception:
        return ''

def _resolve_po_import_target_itemcode(location_code: int, invoice_uom_raw: Any, source_rawabicode: Any) -> Tuple[Optional[int], str]:
    """
    Resolve **current tenant** ITEMMASTER.ITEMCODE only via RAWABICODE (+ UOM), never via source invoice item code.

    Order: RAWABICODE + UOM → RAWABICODE only when invoice UOM mismatches (flagged in UI).

    Returns (target_itemcode or None, match_kind).
    """
    uom_n = _normalize_po_import_uom(invoice_uom_raw)
    raw_s = _normalize_po_import_rawabi_str(source_rawabicode)
    if raw_s:
        ic = _lookup_itemcode_by_rawabicode_and_uom_current(location_code, raw_s, uom_n)
        if ic:
            return (ic, 'rawabi_uom')
        ic3 = _lookup_itemcode_by_rawabicode_only_current(location_code, raw_s)
        if ic3:
            return (ic3, 'rawabi_uom_mismatch')
    return (None, '')

def fetch_sales_invoice_lines_for_po_import(source_tenant_id: str, bill_no: int, target_location_code: int) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Read BILLHDR/BILLDTL from another tenant database by bill number. Each line is matched on the
    **current** tenant by **RAWABICODE + invoice unit (UOM)** against ITEMMASTER.BASEUOM or
    ITEMALTERNATEUOMMAP (source RAWABICODE from source ITEMMASTER when available).

    Fallback when RAWABICODE is missing from the invoice JOIN: **read RAWABICODE from source ITEMMASTER**
    by invoice item code + location, then match on the current tenant only by RAWABICODE (+ UOM).

    When RAWABICODE matches but invoice UOM does not match base/alternate UOM, the line is still matched
    with ``match_kind`` ``rawabi_uom_mismatch`` and ``uom_mismatch`` True (UI highlights the row).

    Item names use **ITEMNAME** (English column) only — not merged Arabic display names.

    Lines with no ITEMMASTER match on the current tenant are still returned in ``matched`` with
    ``no_master_match`` True. Their grid ``itemcode`` field carries **RAWABICODE** when known from the
    invoice/source master (otherwise falls back to source invoice item code). User must replace with a
    valid current-tenant item code before save.

    ``unmatched`` is reserved for API symmetry and is typically empty.

    Returns payload keys: header, matched, unmatched.
    """
    tid = (source_tenant_id or '').strip()
    if not tid:
        return (False, 'Source tenant is required.', {})
    try:
        bn = int(bill_no)
    except (TypeError, ValueError):
        return (False, 'Invalid bill number.', {})
    if bn <= 0:
        return (False, 'Invalid bill number.', {})
    try:
        loc_tgt = int(target_location_code)
    except (TypeError, ValueError):
        loc_tgt = 1
    empty: Dict[str, Any] = {'header': None, 'matched': [], 'unmatched': []}

    def _cols(cur: Any, table_u: str) -> Set[str]:
        cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :t', {'t': table_u.upper()})
        return {str(r[0]).upper() for r in cur.fetchall() or []}
    try:
        with _po_import_source_connection(tid) as conn:
            with conn.cursor() as cur:
                bh_cols = _cols(cur, 'BILLHDR')
                bd_cols = _cols(cur, 'BILLDTL')
                if not bh_cols or 'BILLNO' not in bh_cols:
                    return (False, 'BILLHDR not found in source database.', empty)
                if not bd_cols or 'BILLNO' not in bd_cols or 'ITEMCODE' not in bd_cols:
                    return (False, 'BILLDTL not found or missing ITEMCODE in source database.', empty)
                loc_sel = 'LOCATIONCODE' if 'LOCATIONCODE' in bh_cols else None
                dt_sel = 'BILLDATE' if 'BILLDATE' in bh_cols else None
                reset_sel = 'RESETNO' if 'RESETNO' in bh_cols else None
                sel_parts = ['BILLNO']
                if loc_sel:
                    sel_parts.append(loc_sel)
                if dt_sel:
                    sel_parts.append(dt_sel)
                if reset_sel:
                    sel_parts.append(reset_sel)
                where_h = ['BILLNO = :bn']
                if 'DELFLAG' in bh_cols:
                    where_h.append("(DELFLAG IS NULL OR NVL(DELFLAG,'N') <> 'Y')")
                if 'BILLSTATUS' in bh_cols:
                    where_h.append("(BILLSTATUS IS NULL OR UPPER(TRIM(BILLSTATUS)) <> 'V')")
                order_hdr_parts: List[str] = []
                if loc_sel:
                    order_hdr_parts.append(f'{loc_sel} ASC')
                if reset_sel:
                    order_hdr_parts.append(f'{reset_sel} DESC')
                order_loc = ', '.join(order_hdr_parts) if order_hdr_parts else 'BILLNO'
                hdr_sql = f"\n                    SELECT {', '.join(sel_parts)}\n                    FROM (\n                        SELECT {', '.join(sel_parts)}\n                        FROM BILLHDR\n                        WHERE {' AND '.join(where_h)}\n                        ORDER BY {order_loc}\n                    )\n                    WHERE ROWNUM = 1\n                "
                cur.execute(hdr_sql, {'bn': bn})
                hdr_row = cur.fetchone()
                if not hdr_row:
                    return (False, 'Sales invoice not found for this bill number.', empty)
                desc = [d[0].lower() for d in cur.description or []]
                hdr_dict = dict(zip(desc, [dbm._materialize_db_value(v) for v in hdr_row]))
                src_loc = int(hdr_dict.get('locationcode') or 0) if loc_sel else 0
                qty_col = None
                for _qc in ('QUANTITY', 'QTY', 'SALESQTY', 'QTYORDERED', 'ORDERQTY', 'BILLQTY'):
                    if _qc in bd_cols:
                        qty_col = _qc
                        break
                if not qty_col:
                    return (False, 'BILLDTL has no quantity column (QUANTITY/QTY…).', empty)
                rate_col = 'RATE' if 'RATE' in bd_cols else None
                disc_col = 'ITDISC' if 'ITDISC' in bd_cols else 'DISCOUNT' if 'DISCOUNT' in bd_cols else None
                sl_col = 'SLNO' if 'SLNO' in bd_cols else None
                uom_col = None
                for _uomc in ('UNITOFMEASUREMENT', 'UOM'):
                    if _uomc in bd_cols:
                        uom_col = _uomc
                        break
                sel_d = ['ITEMCODE', qty_col]
                if rate_col:
                    sel_d.append(rate_col)
                if disc_col:
                    sel_d.append(disc_col)
                if sl_col:
                    sel_d.append(sl_col)
                if uom_col:
                    sel_d.append(uom_col)
                sel_exprs = [f'd.{c}' for c in sel_d]
                params_d: Dict[str, Any] = {'bn': bn}
                if src_loc and 'LOCATIONCODE' in bd_cols:
                    params_d['sloc'] = src_loc
                im_cols = _cols(cur, 'ITEMMASTER')
                join_fragment = ''
                if im_cols and 'ITEMCODE' in im_cols and ('RAWABICODE' in im_cols):
                    sel_exprs.append('im.RAWABICODE AS SRC_RAWABICODE')
                    join_on = 'im.ITEMCODE = d.ITEMCODE'
                    if 'LOCATIONCODE' in im_cols and 'LOCATIONCODE' in bd_cols:
                        join_on += ' AND im.LOCATIONCODE = d.LOCATIONCODE'
                    elif src_loc and 'LOCATIONCODE' in im_cols:
                        join_on += ' AND im.LOCATIONCODE = :jloc'
                        params_d['jloc'] = src_loc
                    join_fragment = f' LEFT JOIN ITEMMASTER im ON {join_on} '
                else:
                    sel_exprs.append('CAST(NULL AS VARCHAR2(240)) AS SRC_RAWABICODE')
                where_d = ['d.BILLNO = :bn']
                if src_loc and 'LOCATIONCODE' in bd_cols:
                    where_d.append('d.LOCATIONCODE = :sloc')
                if reset_sel and 'RESETNO' in bd_cols:
                    hdr_rn_raw = hdr_dict.get('resetno')
                    if hdr_rn_raw is not None:
                        try:
                            params_d['d_rn'] = int(hdr_rn_raw)
                            where_d.append('d.RESETNO = :d_rn')
                        except (TypeError, ValueError):
                            pass
                order_d = f'd.{sl_col} ASC' if sl_col else 'd.ITEMCODE'
                dtl_sql = f"\n                    SELECT {', '.join(sel_exprs)}\n                    FROM BILLDTL d\n                    {join_fragment}\n                    WHERE {' AND '.join(where_d)}\n                    ORDER BY {order_d}\n                "
                cur.execute(dtl_sql, params_d)
                dcols = [d[0].lower() for d in cur.description or []]
                raw_lines = [dict(zip(dcols, [dbm._materialize_db_value(v) for v in row])) for row in cur.fetchall() or []]
    except ValueError as ve:
        return (False, str(ve) or 'Invalid tenant.', empty)
    except Exception as e:
        return (False, str(e) or 'Failed to read source invoice.', empty)
    hdr_rn_out: Optional[int] = None
    try:
        _hr = hdr_dict.get('resetno')
        if _hr is not None:
            hdr_rn_out = int(_hr)
    except (TypeError, ValueError):
        hdr_rn_out = None
    header_out = {'billno': bn, 'locationcode': src_loc, 'billdate': _serialize_oracle_date(hdr_dict.get('billdate')), 'resetno': hdr_rn_out, 'source_tenant_id': tid}
    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    rk = qty_col.lower()
    rr = rate_col.lower() if rate_col else None
    rd = disc_col.lower() if disc_col else None
    rs = sl_col.lower() if sl_col else None
    ru = uom_col.lower() if uom_col else None
    try:
        for ln in raw_lines:
            try:
                sic = int(float(ln.get('itemcode') or 0))
            except (TypeError, ValueError):
                sic = 0
            qty = float(ln.get(rk) or 0)
            rate = float(ln.get(rr) or 0) if rr else 0.0
            disc = float(ln.get(rd) or 0) if rd else 0.0
            slno = int(float(ln.get(rs) or 0)) if rs else len(matched) + len(unmatched) + 1
            uom_display = str(ln.get(ru) or '').strip() or 'NOS' if ru else 'NOS'
            src_raw = _normalize_po_import_rawabi_str(ln.get('src_rawabicode'))
            if not src_raw and sic > 0:
                src_raw = fetch_rawabicode_from_source_itemmaster(tid, src_loc, sic)
            if sic <= 0 or qty == 0:
                continue
            tgt_ic, match_kind = _resolve_po_import_target_itemcode(loc_tgt, uom_display, src_raw)
            base_um: Dict[str, Any] = {'slno': slno, 'source_itemcode': sic, 'source_rawabicode': src_raw or None, 'invoice_uom': uom_display, 'quantity': qty, 'rate': rate, 'discount': disc, 'uom': uom_display}

            def _append_no_master_match_line() -> None:
                src_nm = fetch_itemname_from_source_itemmaster(tid, src_loc, sic)
                nm = (src_nm or '').strip() or 'NO MASTER MATCH — fix item'
                raw_disp = _normalize_po_import_rawabi_str(src_raw)
                grid_ref = raw_disp if raw_disp else str(sic)
                matched.append({**base_um, 'itemcode': grid_ref, 'itemname': nm, 'barcode': '', 'match_kind': 'no_master_match', 'no_master_match': True, 'uom_mismatch': False})
            if not tgt_ic:
                _append_no_master_match_line()
                continue
            item_row = dbm.get_item_by_code(tgt_ic, loc_tgt)
            if not item_row:
                _append_no_master_match_line()
                continue
            try:
                resolved_ic = int(float(item_row.get('itemcode') or tgt_ic or 0))
            except (TypeError, ValueError):
                resolved_ic = int(tgt_ic)
            if resolved_ic <= 0:
                _append_no_master_match_line()
                continue
            name = _po_import_itemname_english_only(item_row)
            barcode = str(item_row.get('manufacturerid') or item_row.get('rawabicode') or '').strip()
            uom_mismatch = match_kind == 'rawabi_uom_mismatch'
            matched.append({**base_um, 'itemcode': str(resolved_ic), 'itemname': name, 'barcode': barcode, 'match_kind': match_kind, 'uom_mismatch': uom_mismatch, 'no_master_match': False})
    except Exception as exc:
        return (False, str(exc) or 'Failed to process invoice lines.', empty)
    return (True, '', {'header': header_out, 'matched': matched, 'unmatched': unmatched})

def check_item_exists_by_rawabicode_for_tenant(tenant_id: str, rawabicode: str, location_code: int) -> Dict[str, Any]:
    """Check if target tenant has item with same RAWABICODE in ITEMMASTER."""
    rawabi = (rawabicode or '').strip()
    if not rawabi:
        return {'exists': False, 'itemcode': None, 'itemname': None}
    try:
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                cur.execute('\n                    SELECT ITEMCODE, ITEMNAME\n                    FROM ITEMMASTER\n                    WHERE LOCATIONCODE = :loc\n                      AND TRIM(TO_CHAR(RAWABICODE)) = TRIM(:rawabi)\n                    ', {'loc': int(location_code), 'rawabi': rawabi})
                row = cur.fetchone()
                if not row:
                    return {'exists': False, 'itemcode': None, 'itemname': None}
                return {'exists': True, 'itemcode': row[0], 'itemname': row[1]}
    except Exception:
        return {'exists': False, 'itemcode': None, 'itemname': None}

def get_item_details_by_rawabicode_for_tenant(tenant_id: str, rawabicode: str, location_code: int) -> Optional[Dict[str, Any]]:
    """Get item details by RAWABICODE from tenant ITEMMASTER for a location."""
    rawabi = (rawabicode or '').strip()
    if not rawabi:
        return None
    try:
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
                im_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                uom_col = 'BASEUOM' if 'BASEUOM' in im_cols else 'UNITOFMEASUREMENT' if 'UNITOFMEASUREMENT' in im_cols else 'UOM' if 'UOM' in im_cols else None
                if 'RAWABICODE' not in im_cols or 'ITEMNAME' not in im_cols:
                    return None
                uom_sql = uom_col if uom_col else 'CAST(NULL AS VARCHAR2(30))'
                cost_sql = 'COSTPRICE' if 'COSTPRICE' in im_cols else 'CAST(NULL AS NUMBER)'
                retail_sql = 'RETAILPRICE' if 'RETAILPRICE' in im_cols else 'CAST(NULL AS NUMBER)'
                mfg_sql = 'MANUFACTURERID' if 'MANUFACTURERID' in im_cols else 'CAST(NULL AS VARCHAR2(240))'
                stock_sql = _itemmaster_stock_qty_sql(im_cols)
                cur.execute(f'\n                    SELECT RAWABICODE, {mfg_sql}, ITEMNAME, {uom_sql}, {cost_sql}, {retail_sql}, ({stock_sql})\n                    FROM ITEMMASTER\n                    WHERE LOCATIONCODE = :loc\n                      AND TRIM(TO_CHAR(RAWABICODE)) = TRIM(:rawabi)\n                    ', {'loc': int(location_code), 'rawabi': rawabi})
                row = cur.fetchone()
                if not row:
                    return None
                return {'rawabicode': row[0], 'manufacturerid': row[1], 'itemname': row[2], 'baseuom': row[3], 'costprice': row[4], 'retailprice': row[5], 'currentstock': row[6]}
    except Exception:
        return None
_ITEMMASTER_ITEMNAME_MAX = 50

def _clip_itemmaster_item_name(name: Any) -> str:
    s = str(name or '').strip().upper()
    if not s:
        return ''
    return s[:_ITEMMASTER_ITEMNAME_MAX]

def _itemmaster_ownproduct_char(item_data: Dict[str, Any]) -> str:
    v = item_data.get('own_product')
    if v is True:
        return 'Y'
    s = str(v or '').strip().upper()
    return 'Y' if s in ('Y', 'YES', '1', 'TRUE', 'ON') else 'N'

def _itemmaster_sync_ownproduct_column(cur: Any, item_cols: set, item_data: Dict[str, Any], item_code: int, location_code: int) -> None:
    """Ensure ITEMMASTER.OWNPRODUCT exists and set Y/N from ``item_data['own_product']``."""
    if 'OWNPRODUCT' not in item_cols:
        try:
            cur.execute('ALTER TABLE ITEMMASTER ADD OWNPRODUCT CHAR(1)')
            item_cols.add('OWNPRODUCT')
        except Exception:
            return
    try:
        cur.execute('\n            UPDATE ITEMMASTER\n            SET OWNPRODUCT = :op\n            WHERE ITEMCODE = :item_code\n              AND LOCATIONCODE = :location_code\n            ', {'op': _itemmaster_ownproduct_char(item_data), 'item_code': int(item_code), 'location_code': int(location_code)})
    except Exception:
        pass

def _cx_oracle_named_binds(sql: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Subset ``params`` to names referenced as ``:name`` in ``sql``.

    Thin oracledb can raise ORA-01036 when the bind dict contains keys not used by the statement.
    """
    names = set(re.findall(':([a-zA-Z_][a-zA-Z0-9_]*)', sql))
    missing = names - set(params.keys())
    if missing:
        raise KeyError(f'ITEMMASTER SQL missing bind keys: {sorted(missing)}')
    return {k: params[k] for k in names}

def _cursor_safe_rows(cur: Any, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Same semantics as ``db._safe_rows`` but on an existing cursor (one transaction)."""
    from db.oracle_driver import cx_Oracle

    def _filter_bind_params(sql: str, bind_params: Dict[str, Any]) -> Dict[str, Any]:
        names = [m.group(1).lower() for m in re.finditer(':([A-Za-z_][A-Za-z0-9_]*)', sql or '')]
        if not names:
            return bind_params
        lower_map = {str(k).lower(): v for k, v in bind_params.items()}
        return {name: lower_map.get(name) for name in names}
    try:
        try:
            cur.execute(query, params)
        except cx_Oracle.DatabaseError as e:
            if 'ORA-01036' in str(e) and isinstance(params, dict):
                cur.execute(query, _filter_bind_params(query, params))
            else:
                raise
        if not cur.description:
            return []
        columns = [col[0].lower() for col in cur.description]
        return [dict(zip(columns, [dbm._materialize_db_value(v) for v in row])) for row in cur.fetchall()]
    except cx_Oracle.DatabaseError:
        return []

def _next_itemalternate_slno_cursor(cur: Any, location_code: int, item_code: int) -> int:
    query = '\n        SELECT NVL(MAX(SLNO), 0) + 1 AS NEXT_SLNO\n        FROM ITEMALTERNATEUOMMAP\n        WHERE LOCATIONCODE = :location_code\n        AND ITEMCODE = :item_code\n    '
    rows = _cursor_safe_rows(cur, query, {'location_code': location_code, 'item_code': item_code})
    if rows and rows[0].get('next_slno') is not None:
        try:
            return int(rows[0]['next_slno'])
        except (ValueError, TypeError):
            return 1
    return 1

def _normalize_alternate_uom_code(raw: Any) -> str:
    """UOM code only — strip ``"CODE - Name"`` display forms from pickers; uppercase to match UNITOFMEASUREMENT (Oracle FK is usually case-sensitive)."""
    s = str(raw or '').strip()
    if not s:
        return ''
    if ' - ' in s:
        s = s.split(' - ', 1)[0].strip()
    return s.upper()

def _itemmaster_price_num(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0

def ensure_itemalternateuommap_extension_columns(*, conn: Optional[Any] = None, cur: Optional[Any] = None) -> None:
    """Add DESCRIPTION and IS_BASE (base variant linked to ITEMMASTER) when missing."""
    global _ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY
    if _ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY and cur is None and conn is None:
        return
    if not dbm._table_exists('ITEMALTERNATEUOMMAP'):
        _ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY = True
        return

    def _run(run_cur: Any) -> None:
        try:
            run_cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMALTERNATEUOMMAP'")
            cols = {str(r[0] or '').upper() for r in (run_cur.fetchall() or [])}
        except Exception:
            cols = {c.upper() for c in (dbm._get_table_columns('ITEMALTERNATEUOMMAP') or [])}
        if 'DESCRIPTION' not in cols:
            try:
                run_cur.execute('ALTER TABLE ITEMALTERNATEUOMMAP ADD DESCRIPTION VARCHAR2(500)')
            except Exception:
                pass
        if 'IS_BASE' not in cols:
            try:
                run_cur.execute("ALTER TABLE ITEMALTERNATEUOMMAP ADD IS_BASE CHAR(1) DEFAULT 'N'")
            except Exception:
                pass

    if cur is not None:
        _run(cur)
        return
    if conn is not None:
        # Re-use an open cursor when callers pass one by mistake as ``conn``.
        if callable(getattr(conn, 'cursor', None)):
            with conn.cursor() as run_cur:
                _run(run_cur)
        else:
            _run(conn)
        return
    cols_before = {c.upper() for c in (dbm._get_table_columns('ITEMALTERNATEUOMMAP') or [])}
    if 'DESCRIPTION' in cols_before and 'IS_BASE' in cols_before:
        _ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY = True
        return
    with dbm._get_connection() as c:
        with c.cursor() as run_cur:
            _run(run_cur)
        try:
            c.commit()
        except Exception:
            pass
    dbm._TABLE_COLUMNS_CACHE.pop('ITEMALTERNATEUOMMAP', None)
    _ITEMALTERNATEUOMMAP_EXTENSION_COLUMNS_READY = True

def _itemalternateuommap_has_extension_columns() -> Tuple[bool, bool]:
    cols = {c.upper() for c in (dbm._get_table_columns('ITEMALTERNATEUOMMAP') or [])}
    return ('DESCRIPTION' in cols, 'IS_BASE' in cols)

def itemalternateuommap_select_sql() -> str:
    """SELECT list for ITEMALTERNATEUOMMAP including optional DESCRIPTION / IS_BASE."""
    has_desc, has_base = _itemalternateuommap_has_extension_columns()
    parts = [
        'LOCATIONCODE',
        'SLNO',
        'ITEMCODE',
        'ALTERNATEUOMCODE',
        'MANUFACTURERID',
        'CONVERSIONFACTOR',
        'COSTPRICE',
        'WHOLESALEPRICE',
        'RETAILPRICE',
        'THIRDPRICE',
        'BRANCHPRICE',
    ]
    if has_desc:
        parts.append('DESCRIPTION')
    if has_base:
        parts.append("NVL(IS_BASE, 'N') AS IS_BASE")
    return ', '.join(parts)

def _alternate_row_is_base_flag(data: Dict[str, Any]) -> bool:
    if str(data.get('is_base') or data.get('IS_BASE') or '').strip().upper() in ('Y', '1', 'TRUE'):
        return True
    return bool(data.get('mirror_itemmaster'))

def _alternate_uom_is_itemmaster_mirror(data: Dict[str, Any], base_uom: str, alt_uom: str, conversion_factor: Any, alt_barcode: str) -> bool:
    """First variant row may mirror ITEMMASTER: same UOM, barcode, factor 1."""
    if data.get('mirror_itemmaster'):
        return True
    base_n = _normalize_alternate_uom_code(base_uom)
    alt_n = _normalize_alternate_uom_code(alt_uom)
    if not base_n or not alt_n or base_n != alt_n:
        return False
    try:
        if abs(float(conversion_factor or 0) - 1.0) > 1e-09:
            return False
    except (TypeError, ValueError):
        return False
    master_bc = str(data.get('item_manufacturer_id') or data.get('mirror_manufacturer_id') or '').strip().upper()
    alt_bc = str(alt_barcode or '').strip().upper()
    return bool(master_bc and alt_bc and master_bc == alt_bc)

def build_default_alternate_uom_payload_for_new_item(
    item_data: Dict[str, Any],
    *,
    uom_db_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Default ITEMALTERNATEUOMMAP row #1 mirrors ITEMMASTER (same barcode, base UOM, factor 1)."""
    if not dbm._table_exists('ITEMALTERNATEUOMMAP', db_key=uom_db_key):
        return None
    try:
        loc = int(item_data.get('location_code') or 0)
        ic = int(float(str(item_data.get('item_code') or '').strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        return None
    if loc <= 0 or ic <= 0:
        return None
    base_uom = _normalize_alternate_uom_code(item_data.get('base_uom'))
    if not base_uom:
        logging.getLogger(__name__).info('skip default ITEMALTERNATEUOMMAP for item %s: base UOM missing', ic)
        return None
    if not dbm.uom_code_exists_for_location(base_uom, loc, uom_db_key):
        logging.getLogger(__name__).info(
            'skip default ITEMALTERNATEUOMMAP for item %s: base UOM %s not in UNITOFMEASUREMENT',
            ic,
            base_uom,
        )
        return None
    master_barcode = str(item_data.get('manufacturer_id') or ic).strip()
    factor = 1.0
    master_cost = _itemmaster_price_num(item_data.get('cost_price'))
    return {
        'location_code': loc,
        'item_code': ic,
        'slno': '1',
        'alternate_uom_code': base_uom,
        'manufacturer_id': master_barcode,
        'base_uom': base_uom,
        'conversion_factor': factor,
        'cost_price': round(factor * master_cost, 3),
        'wholesale_price': _itemmaster_price_num(item_data.get('wholesale_price')),
        'retail_price': _itemmaster_price_num(item_data.get('retail_price')),
        'third_price': _itemmaster_price_num(item_data.get('third_price')),
        'branch_price': _itemmaster_price_num(item_data.get('branch_price')),
        'description': str(item_data.get('description') or item_data.get('item_name') or '')[:500],
        'is_base': True,
        'mirror_itemmaster': True,
        'item_manufacturer_id': master_barcode,
    }

def _build_base_alternate_payload_from_itemmaster(item_data: Dict[str, Any], *, slno: Any = '1') -> Optional[Dict[str, Any]]:
    """Payload for the base variant row (always mirrors ITEMMASTER header)."""
    try:
        loc = int(item_data.get('location_code') or 0)
        ic = int(float(str(item_data.get('item_code') or '').strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        return None
    if loc <= 0 or ic <= 0:
        return None
    base_uom = _normalize_alternate_uom_code(item_data.get('base_uom'))
    if not base_uom:
        return None
    master_barcode = str(item_data.get('manufacturer_id') or ic).strip()
    factor = 1.0
    master_cost = _itemmaster_price_num(item_data.get('cost_price'))
    return {
        'location_code': loc,
        'item_code': ic,
        'slno': str(slno or '1').strip() or '1',
        'alternate_uom_code': base_uom,
        'manufacturer_id': master_barcode,
        'base_uom': base_uom,
        'conversion_factor': factor,
        'cost_price': round(factor * master_cost, 3),
        'wholesale_price': _itemmaster_price_num(item_data.get('wholesale_price')),
        'retail_price': _itemmaster_price_num(item_data.get('retail_price')),
        'third_price': _itemmaster_price_num(item_data.get('third_price')),
        'branch_price': _itemmaster_price_num(item_data.get('branch_price')),
        'description': str(item_data.get('description') or item_data.get('item_name') or '')[:500],
        'is_base': True,
        'mirror_itemmaster': True,
        'item_manufacturer_id': master_barcode,
    }

def _merge_base_alternate_payloads_from_itemmaster(
    item_data: Dict[str, Any],
    payloads: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Ensure exactly one base row; overwrite its fields from ITEMMASTER (connected to base UOM / barcode / prices)."""
    base_tpl = _build_base_alternate_payload_from_itemmaster(item_data)
    if not base_tpl:
        return list(payloads or [])
    base_uom = _normalize_alternate_uom_code(item_data.get('base_uom'))
    master_bc = str(item_data.get('manufacturer_id') or item_data.get('item_code') or '').strip()
    out: List[Dict[str, Any]] = []
    base_merged = False
    for raw in payloads or []:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        alt_uom = _normalize_alternate_uom_code(p.get('alternate_uom_code'))
        is_base = _alternate_row_is_base_flag(p) or _alternate_uom_is_itemmaster_mirror(
            p, base_uom, alt_uom, p.get('conversion_factor'), p.get('manufacturer_id'),
        )
        if is_base:
            if base_merged:
                continue
            merged = dict(base_tpl)
            if p.get('slno'):
                merged['slno'] = str(p.get('slno')).strip()
            out.append(merged)
            base_merged = True
        else:
            p['is_base'] = False
            if 'description' not in p:
                p['description'] = str(p.get('description') or '')[:500]
            out.append(p)
    if not base_merged:
        out.insert(0, base_tpl)
    return out


def _base_alternate_row_hit_sql(*, has_base: bool) -> str:
    """Find existing base-mirror row; tolerate NULL CONVERSIONFACTOR (common on DB-trigger inserts)."""
    if has_base:
        return """
        SELECT SLNO AS slno FROM (
            SELECT SLNO FROM ITEMALTERNATEUOMMAP
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
              AND (
                  NVL(IS_BASE, 'N') = 'Y'
                  OR UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))
                  OR UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
              )
            ORDER BY
                CASE WHEN NVL(IS_BASE, 'N') = 'Y' THEN 0 ELSE 1 END,
                CASE WHEN UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code)) THEN 0 ELSE 1 END,
                CASE WHEN ABS(NVL(CONVERSIONFACTOR, 1) - 1) < 0.000001 THEN 0 ELSE 1 END,
                SLNO
        ) WHERE ROWNUM <= 1
        """
    return """
        SELECT SLNO AS slno FROM (
            SELECT SLNO FROM ITEMALTERNATEUOMMAP
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
              AND (
                  UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))
                  OR UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
              )
            ORDER BY
                CASE WHEN UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code)) THEN 0 ELSE 1 END,
                CASE WHEN ABS(NVL(CONVERSIONFACTOR, 1) - 1) < 0.000001 THEN 0 ELSE 1 END,
                SLNO
        ) WHERE ROWNUM <= 1
        """


def _prune_duplicate_manufacturer_id_rows_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    manufacturer_id: str,
    keep_slno: int,
) -> None:
    """Delete other alternate rows on this item that share the same barcode (UK_ITEMALTERNATEUOMMAP_MANUF)."""
    bc = str(manufacturer_id or '').strip()
    if not bc:
        return
    try:
        keep = int(keep_slno)
    except (TypeError, ValueError):
        return
    cur.execute(
        """
        DELETE FROM ITEMALTERNATEUOMMAP
        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
          AND SLNO <> :keep_slno
          AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
        """,
        {
            'location_code': int(location_code),
            'item_code': int(item_code),
            'keep_slno': keep,
            'manufacturer_id': bc,
        },
    )


def _preferred_alternate_slno_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    *,
    manufacturer_id: Optional[str] = None,
    alternate_uom_code: Optional[str] = None,
) -> Optional[int]:
    """Pick one alternate row to update: IS_BASE=Y first, else lowest SLNO (legacy duplicates untouched)."""
    where_parts = [
        'LOCATIONCODE = :location_code',
        'ITEMCODE = :item_code',
    ]
    params: Dict[str, Any] = {
        'location_code': int(location_code),
        'item_code': int(item_code),
    }
    bc = str(manufacturer_id or '').strip()
    if bc:
        where_parts.append('UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))')
        params['manufacturer_id'] = bc
    uom_n = _normalize_alternate_uom_code(alternate_uom_code) if alternate_uom_code else ''
    if uom_n:
        where_parts.append('UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))')
        params['alternate_uom_code'] = uom_n
    rows = _cursor_safe_rows(
        cur,
        f"""
        SELECT SLNO AS slno FROM (
            SELECT SLNO FROM ITEMALTERNATEUOMMAP
            WHERE {' AND '.join(where_parts)}
            ORDER BY CASE WHEN NVL(IS_BASE, 'N') = 'Y' THEN 0 ELSE 1 END, SLNO
        ) WHERE ROWNUM <= 1
        """,
        params,
    )
    if not rows or rows[0].get('slno') is None:
        return None
    try:
        return int(rows[0]['slno'])
    except (TypeError, ValueError):
        return None


def _alternate_barcode_owner_item_code_cur(
    cur: Any,
    location_code: int,
    manufacturer_id: str,
) -> Optional[int]:
    """Return ITEMCODE owning an alternate barcode, using the active cursor (same transaction)."""
    bc = str(manufacturer_id or '').strip()
    if not bc:
        return None
    rows = _cursor_safe_rows(
        cur,
        """
        SELECT ITEMCODE AS itemcode FROM (
            SELECT ITEMCODE FROM ITEMALTERNATEUOMMAP
            WHERE LOCATIONCODE = :location_code
              AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
            ORDER BY SLNO
        ) WHERE ROWNUM <= 1
        """,
        {'location_code': int(location_code), 'manufacturer_id': bc},
    )
    if not rows or rows[0].get('itemcode') is None:
        return None
    try:
        ic = int(rows[0]['itemcode'])
    except (TypeError, ValueError):
        return None
    return ic if ic > 0 else None


def _clear_other_base_alternate_rows_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    keep_slno: int,
) -> None:
    """Clear IS_BASE on sibling rows after insert/update (avoids ORA-12838 from pre-insert UPDATE)."""
    cur.execute(
        """
        UPDATE ITEMALTERNATEUOMMAP SET IS_BASE = 'N'
        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
          AND NVL(IS_BASE, 'N') = 'Y' AND SLNO <> :slno
        """,
        {'location_code': int(location_code), 'item_code': int(item_code), 'slno': int(keep_slno)},
    )


def _alternate_payloads_include_base_mirror(
    item_data: Dict[str, Any],
    payloads: List[Dict[str, Any]],
) -> bool:
    base_uom = _normalize_alternate_uom_code(item_data.get('base_uom'))
    for raw in payloads or []:
        if not isinstance(raw, dict):
            continue
        alt_uom = _normalize_alternate_uom_code(raw.get('alternate_uom_code'))
        if _alternate_row_is_base_flag(raw) or raw.get('mirror_itemmaster'):
            return True
        if _alternate_uom_is_itemmaster_mirror(
            raw, base_uom, alt_uom, raw.get('conversion_factor'), raw.get('manufacturer_id'),
        ):
            return True
    return False


def _collapse_duplicate_base_alternate_rows_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    base_uom: str,
    keep_slno: int,
) -> None:
    """Remove extra base-mirror rows (e.g. Oracle trigger row + app sync insert)."""
    uom_n = _normalize_alternate_uom_code(base_uom)
    if not uom_n:
        return
    has_desc, has_base = _itemalternateuommap_has_extension_columns()
    dup_sql = """
        SELECT SLNO AS slno FROM ITEMALTERNATEUOMMAP
        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
          AND SLNO <> :keep_slno
          AND (
    """
    if has_base:
        dup_sql += """
              NVL(IS_BASE, 'N') = 'Y'
              OR (
        """
    dup_sql += """
                  UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))
                  AND ABS(NVL(CONVERSIONFACTOR, 1) - 1) < 0.000001
    """
    if has_base:
        dup_sql += """
              )
    """
    dup_sql += """
          )
    """
    dup_params = {
        'location_code': int(location_code),
        'item_code': int(item_code),
        'keep_slno': int(keep_slno),
        'alternate_uom_code': uom_n,
    }
    dups = _cursor_safe_rows(cur, dup_sql, dup_params)
    for row in dups or []:
        sl = row.get('slno')
        if sl is None:
            continue
        try:
            sl_i = int(sl)
        except (TypeError, ValueError):
            continue
        cur.execute(
            """
            DELETE FROM ITEMALTERNATEUOMMAP
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code AND SLNO = :slno
            """,
            {'location_code': int(location_code), 'item_code': int(item_code), 'slno': sl_i},
        )


def sync_base_alternate_row_from_itemmaster_cur(
    cur: Any,
    item_data: Dict[str, Any],
    *,
    auto_dedupe: bool = True,
) -> None:
    """After ITEMMASTER save: upsert IS_BASE row so it stays linked to header (base UOM, barcode, prices, description)."""
    ensure_itemalternateuommap_extension_columns(cur=cur)
    base_payload = _build_base_alternate_payload_from_itemmaster(item_data)
    if not base_payload:
        return
    has_desc, has_base = _itemalternateuommap_has_extension_columns()
    loc = int(base_payload['location_code'])
    ic = int(base_payload['item_code'])
    base_uom = base_payload['alternate_uom_code']
    params = {
        'location_code': loc,
        'item_code': ic,
        'alternate_uom_code': base_uom,
        'manufacturer_id': base_payload['manufacturer_id'],
        'conversion_factor': base_payload['conversion_factor'],
        'cost_price': base_payload['cost_price'],
        'wholesale_price': base_payload['wholesale_price'],
        'retail_price': base_payload['retail_price'],
        'third_price': base_payload['third_price'],
        'branch_price': base_payload['branch_price'],
    }
    if has_desc:
        params['description'] = base_payload.get('description') or ''
    if has_base:
        params['is_base'] = 'Y'
    hit = _cursor_safe_rows(cur, _base_alternate_row_hit_sql(has_base=has_base), params)
    set_parts = [
        'ALTERNATEUOMCODE = :alternate_uom_code',
        'MANUFACTURERID = :manufacturer_id',
        'CONVERSIONFACTOR = :conversion_factor',
        'COSTPRICE = :cost_price',
        'WHOLESALEPRICE = :wholesale_price',
        'RETAILPRICE = :retail_price',
        'THIRDPRICE = :third_price',
        'BRANCHPRICE = :branch_price',
    ]
    if has_desc:
        set_parts.append('DESCRIPTION = :description')
    if has_base:
        set_parts.append("IS_BASE = 'Y'")
    alt_cols = {c.upper() for c in (dbm._get_table_columns('ITEMALTERNATEUOMMAP') or [])}
    stock_col = next((c for c in ('CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK', 'QTYONHAND') if c in alt_cols), None)
    stock_val = item_data.get('current_stock')
    if stock_val is None:
        stock_val = item_data.get('currentstock')
    if stock_val is None:
        stock_val = item_data.get('CURRENTSTOCK')
    if stock_col and stock_val is not None:
        try:
            params['current_stock'] = float(stock_val or 0)
            set_parts.append(f'{stock_col} = :current_stock')
        except (TypeError, ValueError):
            pass
    if hit and hit[0].get('slno') is not None:
        params['slno'] = int(hit[0]['slno'])
        if auto_dedupe:
            _prune_duplicate_manufacturer_id_rows_cur(
                cur, loc, ic, str(params.get('manufacturer_id') or ''), int(params['slno']),
            )
        upd = f"""
            UPDATE ITEMALTERNATEUOMMAP SET {', '.join(set_parts)}
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code AND SLNO = :slno
        """
        cur.execute(upd, _cx_oracle_named_binds(upd, params))
        if has_base:
            _clear_other_base_alternate_rows_cur(cur, loc, ic, int(params['slno']))
        if auto_dedupe:
            _collapse_duplicate_base_alternate_rows_cur(cur, loc, ic, base_uom, int(params['slno']))
        return
    if not hit:
        pref_sl = _preferred_alternate_slno_cur(
            cur, loc, ic,
            manufacturer_id=str(params.get('manufacturer_id') or ''),
        )
    else:
        pref_sl = None
    if pref_sl is not None:
        params['slno'] = int(pref_sl)
        if auto_dedupe:
            _prune_duplicate_manufacturer_id_rows_cur(
                cur, loc, ic, str(params.get('manufacturer_id') or ''), int(params['slno']),
            )
        upd = f"""
            UPDATE ITEMALTERNATEUOMMAP SET {', '.join(set_parts)}
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code AND SLNO = :slno
        """
        cur.execute(upd, _cx_oracle_named_binds(upd, params))
        if has_base:
            _clear_other_base_alternate_rows_cur(cur, loc, ic, int(params['slno']))
        if auto_dedupe:
            _collapse_duplicate_base_alternate_rows_cur(cur, loc, ic, base_uom, int(params['slno']))
        return
    params['slno'] = _next_itemalternate_slno_cursor(cur, loc, ic)
    ins_cols = [
        'LOCATIONCODE', 'SLNO', 'ITEMCODE', 'ALTERNATEUOMCODE', 'MANUFACTURERID',
        'CONVERSIONFACTOR', 'COSTPRICE', 'WHOLESALEPRICE', 'RETAILPRICE', 'THIRDPRICE', 'BRANCHPRICE',
    ]
    ins_vals = [
        ':location_code', ':slno', ':item_code', ':alternate_uom_code', ':manufacturer_id',
        ':conversion_factor', ':cost_price', ':wholesale_price', ':retail_price', ':third_price', ':branch_price',
    ]
    if has_desc:
        ins_cols.append('DESCRIPTION')
        ins_vals.append(':description')
    if has_base:
        ins_cols.append('IS_BASE')
        ins_vals.append(':is_base')
    if stock_col and 'current_stock' in params:
        ins_cols.append(stock_col)
        ins_vals.append(':current_stock')
    ins_sql = f"INSERT INTO ITEMALTERNATEUOMMAP ({', '.join(ins_cols)}) VALUES ({', '.join(ins_vals)})"
    cur.execute(ins_sql, _cx_oracle_named_binds(ins_sql, params))
    if has_base:
        _clear_other_base_alternate_rows_cur(cur, loc, ic, int(params['slno']))
    if auto_dedupe:
        _collapse_duplicate_base_alternate_rows_cur(cur, loc, ic, base_uom, int(params['slno']))

def _itemmaster_row_as_base_sync_payload(row: Dict[str, Any], location_code: int) -> Optional[Dict[str, Any]]:
    """Map ITEMMASTER row dict to payload for sync_base_alternate_row_from_itemmaster_cur."""
    try:
        ic = int(float(str(row.get('itemcode') or row.get('ITEMCODE') or '').strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        return None
    loc = int(location_code or row.get('locationcode') or row.get('LOCATIONCODE') or 0)
    if ic <= 0 or loc <= 0:
        return None
    base_uom = _normalize_alternate_uom_code(row.get('baseuom') or row.get('BASEUOM'))
    if not base_uom:
        return None
    return {
        'location_code': loc,
        'item_code': ic,
        'base_uom': base_uom,
        'manufacturer_id': str(row.get('manufacturerid') or row.get('MANUFACTURERID') or ic).strip(),
        'cost_price': row.get('costprice') if row.get('costprice') is not None else row.get('COSTPRICE'),
        'wholesale_price': row.get('wholesaleprice') if row.get('wholesaleprice') is not None else row.get('WHOLESALEPRICE'),
        'retail_price': row.get('retailprice') if row.get('retailprice') is not None else row.get('RETAILPRICE'),
        'third_price': row.get('thirdprice') if row.get('thirdprice') is not None else row.get('THIRDPRICE'),
        'branch_price': row.get('branchprice') if row.get('branchprice') is not None else row.get('BRANCHPRICE'),
        'description': str(row.get('description') or row.get('DESCRIPTION') or row.get('itemname') or row.get('ITEMNAME') or '')[:500],
        'item_name': str(row.get('itemname') or row.get('ITEMNAME') or ''),
        'current_stock': row.get('currentstock') if row.get('currentstock') is not None else row.get('CURRENTSTOCK'),
    }


def _itemmaster_missing_base_alternate_not_exists_sql(
    im_lc: str,
    im_ic: str,
    im_uom: str,
    alt_tbl: str,
    alt_lc: str,
    alt_ic: str,
    alt_uom: str,
    alt_factor: str,
    alt_is_base: Optional[str],
) -> str:
    if alt_is_base:
        base_match = f"""(
            NVL(altx.{alt_is_base}, 'N') = 'Y'
            OR (UPPER(TRIM(altx.{alt_uom})) = UPPER(TRIM(im.{im_uom}))
                AND ABS(NVL(altx.{alt_factor}, 1) - 1) < 0.000001)
        )"""
    else:
        base_match = f"""(
            UPPER(TRIM(altx.{alt_uom})) = UPPER(TRIM(im.{im_uom}))
            AND ABS(NVL(altx.{alt_factor}, 1) - 1) < 0.000001
        )"""
    return f"""
        NOT EXISTS (
            SELECT 1 FROM {alt_tbl} altx
            WHERE altx.{alt_lc} = im.{im_lc}
              AND altx.{alt_ic} = im.{im_ic}
              AND {base_match}
        )
    """


def count_itemmaster_missing_base_alternate(location_code: int) -> int:
    """ITEMMASTER rows with BASEUOM but no IS_BASE / base mirror row in ITEMALTERNATEUOMMAP."""
    if not dbm._table_exists('ITEMMASTER') or not dbm._table_exists('ITEMALTERNATEUOMMAP'):
        return 0
    imx = dbm._detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    alt_tbl = dbm._detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap']) or 'ITEMALTERNATEUOMMAP'
    im_lc = dbm._detect_column(imx, ['LOCATIONCODE', 'locationcode']) or 'LOCATIONCODE'
    im_ic = dbm._detect_column(imx, ['ITEMCODE', 'itemcode']) or 'ITEMCODE'
    im_uom = dbm._detect_column(imx, ['BASEUOM', 'baseuom', 'UOM']) or 'BASEUOM'
    alt_lc = dbm._detect_column(alt_tbl, ['LOCATIONCODE', 'locationcode']) or 'LOCATIONCODE'
    alt_ic = dbm._detect_column(alt_tbl, ['ITEMCODE', 'itemcode']) or 'ITEMCODE'
    alt_uom = dbm._detect_column(alt_tbl, ['ALTERNATEUOMCODE', 'alternateuomcode']) or 'ALTERNATEUOMCODE'
    alt_factor = dbm._detect_column(
        alt_tbl,
        ['CONVERSIONFACTOR', 'CONVERSION_FACTOR', 'UOMFACTOR', 'FACTOR'],
    ) or 'CONVERSIONFACTOR'
    alt_is_base = dbm._detect_column(alt_tbl, ['IS_BASE', 'is_base'])
    not_exists = _itemmaster_missing_base_alternate_not_exists_sql(
        im_lc, im_ic, im_uom, alt_tbl, alt_lc, alt_ic, alt_uom, alt_factor, alt_is_base,
    )
    q = f"""
        SELECT COUNT(*) AS cnt
        FROM {imx} im
        WHERE im.{im_lc} = :loc
          AND LENGTH(TRIM(NVL(im.{im_uom}, ''))) > 0
          AND {not_exists}
    """
    rows = dbm._safe_rows(q, {'loc': int(location_code)})
    try:
        return int((rows[0] if rows else {}).get('cnt') or 0)
    except (TypeError, ValueError):
        return 0


def fetch_itemmaster_base_alternate_sync_batch(
    location_code: int,
    offset: int,
    limit: int,
    *,
    missing_only: bool = True,
) -> List[int]:
    """Paged ITEMCODE list for base-alternate sync (missing rows or all with BASEUOM)."""
    if not dbm._table_exists('ITEMMASTER') or limit <= 0:
        return []
    if missing_only and not dbm._table_exists('ITEMALTERNATEUOMMAP'):
        return []
    imx = dbm._detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    im_lc = dbm._detect_column(imx, ['LOCATIONCODE', 'locationcode']) or 'LOCATIONCODE'
    im_ic = dbm._detect_column(imx, ['ITEMCODE', 'itemcode']) or 'ITEMCODE'
    im_uom = dbm._detect_column(imx, ['BASEUOM', 'baseuom', 'UOM']) or 'BASEUOM'
    off = max(0, int(offset))
    lim = max(1, min(int(limit), 500))
    hi = off + lim
    extra = ''
    if missing_only:
        alt_tbl = dbm._detect_table(['ITEMALTERNATEUOMMAP', 'itemalternateuommap']) or 'ITEMALTERNATEUOMMAP'
        alt_lc = dbm._detect_column(alt_tbl, ['LOCATIONCODE', 'locationcode']) or 'LOCATIONCODE'
        alt_ic = dbm._detect_column(alt_tbl, ['ITEMCODE', 'itemcode']) or 'ITEMCODE'
        alt_uom = dbm._detect_column(alt_tbl, ['ALTERNATEUOMCODE', 'alternateuomcode']) or 'ALTERNATEUOMCODE'
        alt_factor = dbm._detect_column(
            alt_tbl,
            ['CONVERSIONFACTOR', 'CONVERSION_FACTOR', 'UOMFACTOR', 'FACTOR'],
        ) or 'CONVERSIONFACTOR'
        alt_is_base = dbm._detect_column(alt_tbl, ['IS_BASE', 'is_base'])
        extra = ' AND ' + _itemmaster_missing_base_alternate_not_exists_sql(
            im_lc, im_ic, im_uom, alt_tbl, alt_lc, alt_ic, alt_uom, alt_factor, alt_is_base,
        )
    q = f"""
        SELECT itemcode FROM (
            SELECT im.{im_ic} AS itemcode,
                   ROW_NUMBER() OVER (ORDER BY im.{im_ic}) AS rn
            FROM {imx} im
            WHERE im.{im_lc} = :loc
              AND LENGTH(TRIM(NVL(im.{im_uom}, ''))) > 0
              {extra}
        ) t
        WHERE t.rn > :off AND t.rn <= :hi
    """
    rows = dbm._safe_rows(q, {'loc': int(location_code), 'off': off, 'hi': hi})
    out: List[int] = []
    for r in rows or []:
        try:
            ic = int(float(str(r.get('itemcode') or '').strip()))
        except (TypeError, ValueError):
            continue
        if ic > 0:
            out.append(ic)
    return out


def sync_base_alternate_from_itemmaster_by_code(location_code: int, item_code: int) -> str:
    """Upsert IS_BASE row from ITEMMASTER. Returns created|updated|skipped|error."""
    try:
        ic = int(item_code)
        loc = int(location_code)
    except (TypeError, ValueError):
        return 'skipped:invalid_code'
    if ic <= 0 or loc <= 0:
        return 'skipped:invalid_code'
    row = dbm.get_item_by_code(ic, loc)
    if not row:
        return 'skipped:no_item'
    payload = _itemmaster_row_as_base_sync_payload(row, loc)
    if not payload:
        return 'skipped:no_base_uom'
    missing_before = True
    if dbm._table_exists('ITEMALTERNATEUOMMAP'):
        uoms = dbm.get_item_alternate_uoms(ic, loc) or []
        base_uom = payload.get('base_uom') or ''
        had_base = False
        for u in uoms:
            if str(u.get('is_base') or u.get('IS_BASE') or '').strip().upper() in ('Y', '1', 'TRUE'):
                had_base = True
                break
            if _alternate_uom_is_itemmaster_mirror(
                u, base_uom, u.get('uom') or u.get('alternate_uom_code'),
                u.get('factor') or u.get('conversion_factor'), u.get('barcode') or u.get('manufacturer_id'),
            ):
                had_base = True
                break
        missing_before = not had_base
    with dbm._get_connection() as conn:
        with conn.cursor() as cur:
            sync_base_alternate_row_from_itemmaster_cur(cur, payload)
        conn.commit()
    return 'created' if missing_before else 'updated'


def bulk_sync_itemmaster_base_alternate_batch(
    location_code: int,
    offset: int,
    limit: int,
    *,
    missing_only: bool = True,
) -> Dict[str, Any]:
    """Process one batch: add/refresh IS_BASE alternate rows from ITEMMASTER."""
    loc = int(location_code)
    codes = fetch_itemmaster_base_alternate_sync_batch(loc, offset, limit, missing_only=missing_only)
    created = updated = skipped = failed = 0
    errors: List[str] = []
    samples: List[Dict[str, Any]] = []
    for ic in codes:
        try:
            outcome = sync_base_alternate_from_itemmaster_by_code(loc, ic)
        except Exception as exc:
            failed += 1
            if len(errors) < 30:
                errors.append(f'Item {ic}: {exc}')
            continue
        if outcome == 'created':
            created += 1
        elif outcome == 'updated':
            updated += 1
        elif outcome.startswith('skipped'):
            skipped += 1
        else:
            failed += 1
            if len(errors) < 30:
                errors.append(f'Item {ic}: {outcome}')
            continue
        if len(samples) < 8:
            samples.append({'itemcode': ic, 'result': outcome})
    if missing_only:
        remaining = count_itemmaster_missing_base_alternate(loc)
    else:
        remaining = 0
    next_offset = int(offset) + len(codes)
    done = len(codes) < int(limit)
    if missing_only:
        done = done or remaining <= 0
    return {
        'processed': len(codes),
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'errors': errors,
        'samples': samples,
        'remaining': remaining,
        'next_offset': next_offset,
        'done': done,
    }

_ITEM_PRICE_FIELD_TO_COL = {
    'cost_price': 'COSTPRICE',
    'retail_price': 'RETAILPRICE',
    'wholesale_price': 'WHOLESALEPRICE',
    'third_price': 'THIRDPRICE',
    'branch_price': 'BRANCHPRICE',
}


def _lookup_alternate_uom_by_barcode_trimmed(location_code: int, barcode: str) -> Optional[Dict[str, Any]]:
    bc = str(barcode or '').strip()
    if not bc or not dbm._table_exists('ITEMALTERNATEUOMMAP'):
        return None
    q = """
        SELECT
            LOCATIONCODE AS locationcode,
            SLNO AS slno,
            ITEMCODE AS itemcode,
            ALTERNATEUOMCODE AS alternateuomcode,
            MANUFACTURERID AS manufacturerid,
            CONVERSIONFACTOR AS conversionfactor,
            COSTPRICE AS costprice,
            WHOLESALEPRICE AS wholesaleprice,
            RETAILPRICE AS retailprice,
            THIRDPRICE AS thirdprice,
            BRANCHPRICE AS branchprice
        FROM ITEMALTERNATEUOMMAP
        WHERE LOCATIONCODE = :location_code
          AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
        ORDER BY SLNO
    """
    rows = dbm._safe_rows(q, {'location_code': int(location_code), 'manufacturer_id': bc})
    return rows[0] if rows else None


def _lookup_itemmaster_by_barcode_trimmed(location_code: int, barcode: str) -> Optional[Dict[str, Any]]:
    bc = str(barcode or '').strip()
    if not bc:
        return None
    q = """
        SELECT ITEMCODE AS itemcode
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :location_code
          AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))
    """
    rows = dbm._safe_rows(q, {'location_code': int(location_code), 'manufacturer_id': bc})
    if not rows:
        return None
    try:
        ic = int(rows[0].get('itemcode') or 0)
    except (TypeError, ValueError):
        return None
    if ic <= 0:
        return None
    return dbm.get_item_by_code(ic, int(location_code))


def _partial_price_set_sql(prices: Dict[str, float], col_map: Dict[str, str]) -> Tuple[List[str], Dict[str, Any]]:
    set_parts: List[str] = []
    params: Dict[str, Any] = {}
    for key, col in col_map.items():
        if key not in prices:
            continue
        bind = f'p_{key}'
        set_parts.append(f'{col} = :{bind}')
        params[bind] = float(prices[key])
    return (set_parts, params)


def _update_itemmaster_prices_cur(cur: Any, location_code: int, item_code: int, prices: Dict[str, float]) -> bool:
    set_parts, extra = _partial_price_set_sql(prices, _ITEM_PRICE_FIELD_TO_COL)
    if not set_parts:
        return False
    params = {'location_code': int(location_code), 'item_code': int(item_code), **extra}
    sql = f"""
        UPDATE ITEMMASTER
        SET {', '.join(set_parts)}
        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
    """
    cur.execute(sql, _cx_oracle_named_binds(sql, params))
    return getattr(cur, 'rowcount', 0) != 0


def _update_alternate_uom_prices_cur(
    cur: Any,
    location_code: int,
    item_code: int,
    slno: int,
    prices: Dict[str, float],
) -> bool:
    set_parts, extra = _partial_price_set_sql(prices, _ITEM_PRICE_FIELD_TO_COL)
    if not set_parts:
        return False
    params = {
        'location_code': int(location_code),
        'item_code': int(item_code),
        'slno': int(slno),
        **extra,
    }
    sql = f"""
        UPDATE ITEMALTERNATEUOMMAP
        SET {', '.join(set_parts)}
        WHERE LOCATIONCODE = :location_code
          AND ITEMCODE = :item_code
          AND SLNO = :slno
    """
    cur.execute(sql, _cx_oracle_named_binds(sql, params))
    return getattr(cur, 'rowcount', 0) != 0


def _find_base_alternate_slno(location_code: int, item_code: int, item_row: Dict[str, Any]) -> Optional[int]:
    if not dbm._table_exists('ITEMALTERNATEUOMMAP'):
        return None
    base_uom = _normalize_alternate_uom_code(item_row.get('baseuom') or item_row.get('BASEUOM'))
    header_bc = str(item_row.get('manufacturerid') or item_row.get('MANUFACTURERID') or '').strip()
    for alt in dbm.get_item_alternate_uoms(int(location_code), int(item_code)) or []:
        try:
            slno = int(alt.get('slno') or alt.get('SLNO') or 0)
        except (TypeError, ValueError):
            slno = 0
        if slno <= 0:
            continue
        if str(alt.get('is_base') or alt.get('IS_BASE') or '').strip().upper() in ('Y', '1', 'TRUE'):
            return slno
        if _alternate_uom_is_itemmaster_mirror(
            alt,
            base_uom,
            alt.get('uom') or alt.get('alternateuomcode') or alt.get('ALTERNATEUOMCODE'),
            alt.get('factor') or alt.get('conversionfactor') or alt.get('CONVERSIONFACTOR'),
            alt.get('barcode') or alt.get('manufacturerid') or alt.get('MANUFACTURERID'),
        ):
            return slno
        if base_uom and str(alt.get('alternateuomcode') or alt.get('uom') or '').strip().upper() == base_uom.upper():
            if float(alt.get('conversionfactor') or alt.get('factor') or 1) == 1:
                return slno
    if header_bc:
        for alt in dbm.get_item_alternate_uoms(int(location_code), int(item_code)) or []:
            abc = str(alt.get('manufacturerid') or alt.get('barcode') or '').strip()
            if abc and abc.upper() == header_bc.upper():
                try:
                    return int(alt.get('slno') or 0)
                except (TypeError, ValueError):
                    pass
    return None


def _alternate_row_is_base_for_item(alt_row: Dict[str, Any], item_row: Dict[str, Any]) -> bool:
    if str(alt_row.get('is_base') or alt_row.get('IS_BASE') or '').strip().upper() in ('Y', '1', 'TRUE'):
        return True
    base_uom = _normalize_alternate_uom_code(item_row.get('baseuom') or item_row.get('BASEUOM'))
    return _alternate_uom_is_itemmaster_mirror(
        alt_row,
        base_uom,
        alt_row.get('alternateuomcode') or alt_row.get('uom'),
        alt_row.get('conversionfactor') or alt_row.get('factor'),
        alt_row.get('manufacturerid') or alt_row.get('barcode'),
    )


def update_item_prices_by_barcode(location_code: int, barcode: str, prices: Dict[str, float]) -> Tuple[bool, str]:
    """
    Update price columns on ITEMMASTER and/or ITEMALTERNATEUOMMAP for a barcode.
    Only keys present in ``prices`` are written (cost/retail/wholesale/third/branch).
    """
    bc = str(barcode or '').strip()
    if not bc:
        return (False, 'Barcode is required.')
    if not prices:
        return (False, 'No price columns provided.')
    try:
        loc = int(location_code)
    except (TypeError, ValueError):
        return (False, 'Invalid location code.')
    if loc <= 0:
        return (False, 'Invalid location code.')

    alt = _lookup_alternate_uom_by_barcode_trimmed(loc, bc)
    item_hdr = _lookup_itemmaster_by_barcode_trimmed(loc, bc)
    if not alt and not item_hdr:
        return (False, f'No item found for barcode "{bc}".')

    updated_master = updated_alt = False
    with dbm._get_connection() as conn:
        with conn.cursor() as cur:
            if alt:
                try:
                    ic = int(alt.get('itemcode') or 0)
                    slno = int(alt.get('slno') or 0)
                except (TypeError, ValueError):
                    ic = slno = 0
                if ic > 0 and slno > 0:
                    updated_alt = _update_alternate_uom_prices_cur(cur, loc, ic, slno, prices)
                    item_row = dbm.get_item_by_code(ic, loc) or {}
                    if item_row and _alternate_row_is_base_for_item(alt, item_row):
                        updated_master = _update_itemmaster_prices_cur(cur, loc, ic, prices) or updated_master
            elif item_hdr:
                try:
                    ic = int(item_hdr.get('itemcode') or 0)
                except (TypeError, ValueError):
                    ic = 0
                if ic > 0:
                    base_slno = _find_base_alternate_slno(loc, ic, item_hdr)
                    updated_master = _update_itemmaster_prices_cur(cur, loc, ic, prices)
                    if base_slno:
                        updated_alt = _update_alternate_uom_prices_cur(cur, loc, ic, base_slno, prices) or updated_alt
        conn.commit()

    if not updated_master and not updated_alt:
        return (False, f'Barcode "{bc}" matched but no price columns were applied.')
    parts = []
    if updated_master:
        parts.append('ITEMMASTER')
    if updated_alt:
        parts.append('ITEMALTERNATEUOMMAP')
    return (True, 'Updated ' + ' and '.join(parts) + f' for barcode "{bc}".')


def update_item_costprice_by_itemcode(
    location_code: int,
    item_code: int,
    cost_price: float,
) -> Tuple[bool, str]:
    """
    Update COSTPRICE on ITEMMASTER and the base ITEMALTERNATEUOMMAP row for an item code.
    """
    try:
        loc = int(location_code)
        ic = int(item_code)
        cp = float(cost_price)
    except (TypeError, ValueError):
        return (False, 'Invalid location, item code, or cost price.')
    if loc <= 0 or ic <= 0:
        return (False, 'Invalid location or item code.')

    item_row = dbm.get_item_by_code(ic, loc)
    if not item_row:
        return (False, f'Item {ic} not found at location {loc}.')

    prices = {'cost_price': cp}
    base_slno = _find_base_alternate_slno(loc, ic, item_row)
    updated_master = updated_alt = False
    with dbm._get_connection() as conn:
        with conn.cursor() as cur:
            updated_master = _update_itemmaster_prices_cur(cur, loc, ic, prices)
            if base_slno:
                updated_alt = _update_alternate_uom_prices_cur(cur, loc, ic, base_slno, prices)
        conn.commit()

    if not updated_master:
        return (False, f'Item {ic}: COSTPRICE could not be updated on ITEMMASTER.')
    msg = f'Updated ITEMMASTER cost for item {ic}.'
    if updated_alt:
        msg += ' Base ITEMALTERNATEUOMMAP row updated.'
    elif dbm._table_exists('ITEMALTERNATEUOMMAP'):
        msg += ' No base alternate row found (ITEMMASTER only).'
    return (True, msg)


def _alternate_uom_payloads_for_save(
    item_data: Dict[str, Any],
    is_new: bool,
    alternate_uom_payloads: Optional[List[Dict[str, Any]]],
    *,
    uom_db_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    payloads = list(alternate_uom_payloads or [])
    # New item with no explicit alternates: base row is created once by sync_base_alternate_row_from_itemmaster_cur.
    if is_new and not payloads:
        return []
    return _merge_base_alternate_payloads_from_itemmaster(item_data, payloads)

def save_item_in_tenant(item_data: Dict[str, Any], is_new: bool, tenant_id: str, *, conn: Optional[Any]=None) -> bool:
    """Save full item master row into specific tenant DB.

    With ``conn``, runs without committing (same transaction). Omit ``conn`` for standalone save + commit.
    """
    tid_key = (tenant_id or '').strip()
    raw_lc = item_data.get('location_code')
    location_code: Optional[int] = None
    if raw_lc is not None and str(raw_lc).strip() != '':
        try:
            location_code = int(raw_lc)
        except (TypeError, ValueError):
            try:
                location_code = int(float(str(raw_lc).strip()))
            except (TypeError, ValueError):
                location_code = None
    if location_code is None or location_code <= 0:
        auth_lc = dbm.get_tenant_locationcode_from_auth(tid_key)
        if auth_lc is not None and auth_lc > 0:
            location_code = auth_lc
    if location_code is None or location_code <= 0:
        location_code = 1
    item_code = int(item_data.get('item_code') or 0)
    if item_code <= 0:
        return False
    try:
        dbm.ensure_itemmaster_inventory_extension_columns()
    except Exception:
        pass
    if is_new:
        query = "\n            INSERT INTO ITEMMASTER (\n                LOCATIONCODE, ITEMCODE, CATEGORYCODE, ITEMNAME, MANUFACTURERID,\n                BRANDCODE, SIZECODE, COLORCODE, BASEUOM,\n                COSTPRICE, RETAILPRICE, WHOLESALEPRICE, THIRDPRICE, BRANCHPRICE,\n                MAXIMUMLEVEL, REORDERLEVEL, CURRENTSTOCK, DISCOUNTFLAG,\n                COMPANYCODE, SUPCODE, DEPARTMENTCODE,\n                MAINCATEGORY, REBATE, ITEMNAMEARA, DESCRIPTION,\n                PROPERTY, ORIGIN, QUANTITYLIMIT, PACKING,\n                MINISTRYFACTOR, MINISTRYUNIT, VATPERCENT,\n                SALESACCOUNT, PURCHASEACCOUNT, INVENTORYACCOUNT, COGSACCOUNT,\n                ITEMFLAG, CREATIONFLAG\n            ) VALUES (\n                :location_code, :item_code, :category_code, :item_name, :manufacturer_id,\n                :brand_code, :size_code, :color_code, :base_uom,\n                :cost_price, :retail_price, :wholesale_price, :third_price, :branch_price,\n                :maximum_level, :reorder_level, 0, :discount_flag,\n                :company_code, :sup_code, :department_code,\n                :main_category, :rebate, :item_name_ara, :description,\n                :property, :origin, :quantity_limit, :packing,\n                :ministry_factor, :ministry_unit, :vat_percent,\n                :sales_account, :purchase_account, :inventory_account, :cogs_account,\n                :item_flag, 'B'\n            )\n        "
    else:
        query = '\n            UPDATE ITEMMASTER SET\n                CATEGORYCODE = :category_code,\n                ITEMNAME = :item_name,\n                MANUFACTURERID = :manufacturer_id,\n                BRANDCODE = :brand_code,\n                SIZECODE = :size_code,\n                COLORCODE = :color_code,\n                BASEUOM = :base_uom,\n                COSTPRICE = :cost_price,\n                RETAILPRICE = :retail_price,\n                WHOLESALEPRICE = :wholesale_price,\n                THIRDPRICE = :third_price,\n                BRANCHPRICE = :branch_price,\n                MAXIMUMLEVEL = :maximum_level,\n                REORDERLEVEL = :reorder_level,\n                DISCOUNTFLAG = :discount_flag,\n                COMPANYCODE = :company_code,\n                SUPCODE = :sup_code,\n\n                DEPARTMENTCODE = :department_code,\n                MAINCATEGORY = :main_category,\n                REBATE = :rebate,\n                ITEMNAMEARA = :item_name_ara,\n                DESCRIPTION = :description,\n                PROPERTY = :property,\n                ORIGIN = :origin,\n                QUANTITYLIMIT = :quantity_limit,\n                PACKING = :packing,\n                MINISTRYFACTOR = :ministry_factor,\n                MINISTRYUNIT = :ministry_unit,\n                VATPERCENT = :vat_percent,\n                SALESACCOUNT = :sales_account,\n                PURCHASEACCOUNT = :purchase_account,\n                INVENTORYACCOUNT = :inventory_account,\n                COGSACCOUNT = :cogs_account\n            WHERE ITEMCODE = :item_code AND LOCATIONCODE = :location_code\n        '
    params = {'location_code': location_code, 'item_code': item_code, 'category_code': item_data.get('category_code') or 0, 'item_name': _clip_itemmaster_item_name(item_data.get('item_name', '')), 'manufacturer_id': item_data.get('manufacturer_id', ''), 'brand_code': item_data.get('brand_code') or 0, 'size_code': item_data.get('size_code') or 0, 'color_code': item_data.get('color_code') or 0, 'base_uom': item_data.get('base_uom', ''), 'cost_price': item_data.get('cost_price') or 0, 'retail_price': item_data.get('retail_price') or 0, 'wholesale_price': item_data.get('wholesale_price') or 0, 'third_price': item_data.get('third_price') or 0, 'branch_price': item_data.get('branch_price') or 0, 'maximum_level': item_data.get('maximum_level') or 0, 'reorder_level': item_data.get('reorder_level') or 0, 'discount_flag': item_data.get('discount_flag', 'N'), 'company_code': item_data.get('company_code', ''), 'sup_code': item_data.get('sup_code') or 0, 'department_code': item_data.get('department_code', ''), 'main_category': item_data.get('main_category') or 0, 'rebate': item_data.get('rebate') or 0, 'item_name_ara': item_data.get('item_name_ara', ''), 'description': item_data.get('description', ''), 'property': item_data.get('property_code') or item_data.get('property') or 0, 'origin': item_data.get('origin_code') or item_data.get('origin') or 0, 'quantity_limit': item_data.get('quantity_limit') or 0, 'packing': item_data.get('packing', ''), 'ministry_factor': item_data.get('ministry_factor', ''), 'ministry_unit': item_data.get('ministry_unit', ''), 'vat_percent': item_data.get('vat_percent') or 0, 'sales_account': item_data.get('sales_account', ''), 'purchase_account': item_data.get('purchase_account', ''), 'inventory_account': item_data.get('inventory_account', ''), 'cogs_account': item_data.get('cogs_account', '')}

    def _persist_row(cur: Any) -> None:
        cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
        item_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
        created_by_col = None
        for c in ('CREATEDBY', 'CREATED_BY', 'USERID', 'USERNAME'):
            if c in item_cols:
                created_by_col = c
                break
        created_date_col = None
        for c in ('CREATEDDATE', 'CREATIONDATE', 'CREATED_AT', 'CDATE'):
            if c in item_cols:
                created_date_col = c
                break
        cur.execute(query, _cx_oracle_named_binds(query, params))
        wh_id_val: Optional[int] = None
        raw_wh = item_data.get('default_warehouse_id')
        if raw_wh is not None and str(raw_wh).strip() != '':
            try:
                wh_id_val = int(float(str(raw_wh).strip()))
            except (TypeError, ValueError):
                wh_id_val = None
        if 'DEFAULT_WAREHOUSE_ID' in item_cols:
            cur.execute(f"""
                UPDATE ITEMMASTER
                SET DEFAULT_WAREHOUSE_ID = :wh_id
                WHERE ITEMCODE = :item_code AND LOCATIONCODE = :location_code
            """, {'wh_id': wh_id_val, 'item_code': item_code, 'location_code': location_code})
        if 'RAWABICODE' in item_cols:
            cur.execute('\n                        UPDATE ITEMMASTER\n                        SET RAWABICODE = :item_code\n                        WHERE ITEMCODE = :item_code\n                          AND LOCATIONCODE = :location_code\n                        ', {'item_code': item_code, 'location_code': location_code})
        _itemmaster_sync_ownproduct_column(cur, item_cols, item_data, int(item_code), int(location_code))
        if is_new and (created_by_col or created_date_col):
            set_parts = []
            stamp_params = {'item_code': item_code, 'location_code': location_code}
            created_by_val = (item_data.get('created_by') or '').strip()[:100]
            if created_by_col and created_by_val:
                set_parts.append(f'{created_by_col} = :created_by')
                stamp_params['created_by'] = created_by_val
            if created_date_col:
                set_parts.append(f'{created_date_col} = SYSDATE')
            if set_parts:
                cur.execute(f"\n                            UPDATE ITEMMASTER\n                            SET {', '.join(set_parts)}\n                            WHERE ITEMCODE = :item_code\n                              AND LOCATIONCODE = :location_code\n                            ", stamp_params)
    try:
        if conn is not None:
            with conn.cursor() as cur:
                _persist_row(cur)
            return True
        ensure_itemmaster_account_columns()
        with dbm._get_tenant_connection(tid_key) as c:
            with c.cursor() as cur:
                _persist_row(cur)
            c.commit()
        return True
    except Exception:
        return False

def save_item_alternate_uom_in_tenant(data: Dict[str, Any], tenant_id: str) -> Tuple[bool, Optional[str]]:
    """Insert/update ITEMALTERNATEUOMMAP in a specific tenant DB."""
    params = {'location_code': data.get('location_code'), 'item_code': data.get('item_code'), 'slno': data.get('slno'), 'alternate_uom_code': data.get('alternate_uom_code'), 'manufacturer_id': data.get('manufacturer_id'), 'conversion_factor': data.get('conversion_factor') or 0, 'cost_price': data.get('cost_price') or 0, 'wholesale_price': data.get('wholesale_price') or 0, 'retail_price': data.get('retail_price') or 0, 'third_price': data.get('third_price') or 0, 'branch_price': data.get('branch_price') or 0}
    params['alternate_uom_code'] = _normalize_alternate_uom_code(params.get('alternate_uom_code'))
    alt_uom = str(params.get('alternate_uom_code') or '').strip()
    alt_barcode = str(params.get('manufacturer_id') or '').strip()
    if not alt_uom:
        return (False, 'Alternate UOM code is required.')

    def _bind(*keys: str) -> Dict[str, Any]:
        return {k: params.get(k) for k in keys}
    try:
        try:
            loc_i = int(float(str(params.get('location_code') or '').strip().split(' - ', 1)[0]))
            icode_i = int(float(str(params.get('item_code') or '').strip().split(' - ', 1)[0]))
        except (TypeError, ValueError):
            return (False, 'Invalid location or item code for alternate UOM.')
        if loc_i <= 0 or icode_i <= 0:
            return (False, 'Invalid location or item code for alternate UOM.')
        params['location_code'] = loc_i
        params['item_code'] = icode_i
        base_uom = _normalize_alternate_uom_code(data.get('base_uom'))
        if base_uom and base_uom.upper() == alt_uom.upper() and (not _alternate_uom_is_itemmaster_mirror(data, base_uom, alt_uom, params.get('conversion_factor'), alt_barcode)):
            return (False, 'Alternate UOM cannot match Base UOM. Please use another UOM.')
        if not dbm.uom_code_exists_for_location(alt_uom, loc_i, (tenant_id or '').strip() or None):
            return (False, 'This alternate UOM is not on file for the current branch in Unit of measurement. If your database stores units per location, add this code under Inventory → Unit of measurement for this branch (it may exist for another location only).')
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                slno_raw = str(params.get('slno') or '').strip()
                target_slno: Optional[int] = None
                if slno_raw:
                    try:
                        cand_sl = int(slno_raw)
                    except (ValueError, TypeError):
                        return (False, 'Invalid alternate row.')
                    cur.execute('\n                        SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND SLNO = :cand_sl\n                        ', {**_bind('location_code', 'item_code'), 'cand_sl': cand_sl})
                    hit_sl = cur.fetchone()
                    if hit_sl:
                        target_slno = int(hit_sl[0])
                    else:
                        cur.execute('\n                            SELECT SLNO FROM (\n                                SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                                WHERE LOCATIONCODE = :location_code\n                                  AND ITEMCODE = :item_code\n                                  AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                                ORDER BY SLNO\n                            ) WHERE ROWNUM <= 1\n                            ', _bind('location_code', 'item_code', 'alternate_uom_code'))
                        hit_u = cur.fetchone()
                        if hit_u:
                            target_slno = int(hit_u[0])
                if target_slno is not None:
                    params['slno'] = target_slno
                    cur.execute('\n                        SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                          AND SLNO <> :slno\n                        ', _bind('location_code', 'item_code', 'alternate_uom_code', 'slno'))
                    if cur.fetchone():
                        return (False, 'Alternate UOM already exists for this item. Please use another UOM.')
                    if alt_barcode:
                        cur.execute('\n                            SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                            WHERE LOCATIONCODE = :location_code\n                              AND ITEMCODE = :item_code\n                              AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                              AND SLNO <> :slno\n                            ', _bind('location_code', 'item_code', 'manufacturer_id', 'slno'))
                        if cur.fetchone():
                            return (False, 'Alternate barcode already exists for this item. Please use another barcode.')
                        try:
                            cur.execute('\n                                SELECT ITEMCODE FROM ITEMMASTER\n                                WHERE LOCATIONCODE = :location_code\n                                  AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                                  AND ITEMCODE <> :item_code\n                                ', _bind('location_code', 'manufacturer_id', 'item_code'))
                            if cur.fetchone():
                                return (False, 'Barcode already exists in Itemmaster. Please use another barcode.')
                        except Exception:
                            pass
                    _alt_upd_sql = '\n                        UPDATE ITEMALTERNATEUOMMAP\n                        SET ALTERNATEUOMCODE = :alternate_uom_code,\n                            MANUFACTURERID = :manufacturer_id,\n                            CONVERSIONFACTOR = :conversion_factor,\n                            COSTPRICE = :cost_price,\n                            WHOLESALEPRICE = :wholesale_price,\n                            RETAILPRICE = :retail_price,\n                            THIRDPRICE = :third_price,\n                            BRANCHPRICE = :branch_price\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND SLNO = :slno\n                    '
                    cur.execute(_alt_upd_sql, _cx_oracle_named_binds(_alt_upd_sql, params))
                    rc_upd = getattr(cur, 'rowcount', None)
                    conn.commit()
                    if rc_upd == 0:
                        return (False, 'Alternate UOM update failed.')
                    return (True, None)
                cur.execute('\n                    SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                    WHERE LOCATIONCODE = :location_code\n                      AND ITEMCODE = :item_code\n                      AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                    ', _bind('location_code', 'item_code', 'alternate_uom_code'))
                hit_uom = cur.fetchone()
                if hit_uom:
                    params['slno'] = int(hit_uom[0])
                    cur.execute('\n                        UPDATE ITEMALTERNATEUOMMAP\n                        SET ALTERNATEUOMCODE = :alternate_uom_code,\n                            MANUFACTURERID = :manufacturer_id,\n                            CONVERSIONFACTOR = :conversion_factor,\n                            COSTPRICE = :cost_price,\n                            WHOLESALEPRICE = :wholesale_price,\n                            RETAILPRICE = :retail_price,\n                            THIRDPRICE = :third_price,\n                            BRANCHPRICE = :branch_price\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND SLNO = :slno\n                    ', _bind('location_code', 'item_code', 'slno', 'alternate_uom_code', 'manufacturer_id', 'conversion_factor', 'cost_price', 'wholesale_price', 'retail_price', 'third_price', 'branch_price'))
                    conn.commit()
                    return (True, None)
                if alt_barcode:
                    cur.execute('\n                        SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                        ', _bind('location_code', 'item_code', 'manufacturer_id'))
                    if cur.fetchone():
                        return (False, 'Alternate barcode already exists for this item. Please use another barcode.')
                    try:
                        cur.execute('\n                            SELECT ITEMCODE FROM ITEMMASTER\n                            WHERE LOCATIONCODE = :location_code\n                              AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                              AND ITEMCODE <> :item_code\n                            ', _bind('location_code', 'manufacturer_id', 'item_code'))
                        if cur.fetchone():
                            return (False, 'Barcode already exists in Itemmaster. Please use another barcode.')
                    except Exception:
                        pass
                cur.execute('\n                    SELECT NVL(MAX(SLNO), 0) + 1 AS NEXT_SLNO\n                    FROM ITEMALTERNATEUOMMAP\n                    WHERE LOCATIONCODE = :location_code\n                      AND ITEMCODE = :item_code\n                    ', _bind('location_code', 'item_code'))
                params['slno'] = int((cur.fetchone() or [1])[0] or 1)
                _alt_ins = '\n                    INSERT INTO ITEMALTERNATEUOMMAP (\n                        LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                        CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                    ) VALUES (\n                        :location_code, :slno, :item_code, :alternate_uom_code, :manufacturer_id,\n                        :conversion_factor, :cost_price, :wholesale_price, :retail_price, :third_price, :branch_price\n                    )\n                    '
                cur.execute(_alt_ins, _cx_oracle_named_binds(_alt_ins, params))
            conn.commit()
        return (True, None)
    except Exception as e:
        print(f'[ERROR save_item_alternate_uom_in_tenant] {e}')
        err = str(e)
        if 'ORA-00001' in err or '00001' in err:
            return (False, 'Alternate UOM save blocked: duplicate row (database unique constraint).')
        if 'ORA-02291' in err or '02291' in err:
            return (False, 'Database rejected the row (missing parent key). Often the alternate UOM must exist in UNITOFMEASUREMENT for this same LOCATIONCODE. Add it under Inventory → Unit of measurement for this branch, or ask your DBA which foreign key failed.')
        if len(err) < 220:
            return (False, f'Failed to save alternate UOM: {err}')
        return (False, 'Failed to save alternate UOM.')

def get_item_alternate_uom_for_tenant(tenant_id: str, location_code: int, item_code: int) -> Optional[Dict[str, Any]]:
    """Get first alternate UOM mapping for item from a specific tenant DB."""
    try:
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                cur.execute('\n                    SELECT LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                           CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                    FROM ITEMALTERNATEUOMMAP\n                    WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode\n                    ORDER BY SLNO\n                    ', {'loc': int(location_code), 'icode': int(item_code)})
                row = cur.fetchone()
                if not row:
                    return None
                cols = [str(d[0]).lower() for d in cur.description or []]
                return dict(zip(cols, row))
    except Exception:
        return None

def get_item_alternate_uoms_for_tenant(tenant_id: str, location_code: int, item_code: int) -> List[Dict[str, Any]]:
    """Get all alternate UOM mappings for item from a specific tenant DB."""
    out: List[Dict[str, Any]] = []
    try:
        with dbm._get_tenant_connection((tenant_id or '').strip()) as conn:
            with conn.cursor() as cur:
                cur.execute('\n                    SELECT LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                           CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                    FROM ITEMALTERNATEUOMMAP\n                    WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode\n                    ORDER BY SLNO\n                    ', {'loc': int(location_code), 'icode': int(item_code)})
                cols = [str(d[0]).lower() for d in cur.description or []]
                for row in cur.fetchall() or []:
                    out.append(dict(zip(cols, row)))
    except Exception:
        return []
    return out

def upsert_itemmaster_basic_to_tenant(tenant_id: str, location_code: int, item_code: int, item_name: str, manufacturer_id: str, base_uom: str, cost_price: float=0.0, retail_price: float=0.0, wholesale_price: float=0.0, third_price: float=0.0, branch_price: float=0.0, create_if_missing: bool=True) -> str:
    """Update basic fields if item exists; otherwise insert with defaults."""
    tid = (tenant_id or '').strip()
    if not tid:
        raise ValueError('tenant_id is required.')
    loc = int(location_code or 1)
    icode = int(item_code or 0)
    if icode <= 0:
        raise ValueError('item_code is required.')
    nm = (item_name or '').strip().upper()
    if not nm:
        raise ValueError('item_name is required.')
    uom = (base_uom or '').strip().upper()
    if not uom:
        raise ValueError('base_uom is required.')
    with dbm._get_tenant_connection(tid) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM ITEMMASTER WHERE LOCATIONCODE = :loc AND ITEMCODE = :icode', {'loc': loc, 'icode': icode})
            exists = int((cur.fetchone() or [0])[0] or 0) > 0
            if exists:
                cur.execute('\n                    UPDATE ITEMMASTER\n                    SET ITEMNAME = :item_name,\n                        MANUFACTURERID = :manufacturer_id,\n                        BASEUOM = :base_uom,\n                        COSTPRICE = :cost_price,\n                        RETAILPRICE = :retail_price,\n                        WHOLESALEPRICE = :wholesale_price,\n                        THIRDPRICE = :third_price,\n                        BRANCHPRICE = :branch_price\n                    WHERE LOCATIONCODE = :loc\n                      AND ITEMCODE = :icode\n                    ', {'loc': loc, 'icode': icode, 'item_name': nm, 'manufacturer_id': (manufacturer_id or '').strip(), 'base_uom': uom, 'cost_price': float(cost_price or 0), 'retail_price': float(retail_price or 0), 'wholesale_price': float(wholesale_price or 0), 'third_price': float(third_price or 0), 'branch_price': float(branch_price or 0)})
                conn.commit()
                return 'updated'
            if not create_if_missing:
                raise ValueError('Item not found in target DB.')
            cur.execute("\n                INSERT INTO ITEMMASTER (\n                    LOCATIONCODE, ITEMCODE, CATEGORYCODE, ITEMNAME, MANUFACTURERID,\n                    BRANDCODE, SIZECODE, COLORCODE, BASEUOM,\n                    COSTPRICE, RETAILPRICE, WHOLESALEPRICE, THIRDPRICE, BRANCHPRICE,\n                    MAXIMUMLEVEL, REORDERLEVEL, CURRENTSTOCK, DISCOUNTFLAG,\n                    COMPANYCODE, SUPCODE, DEPARTMENTCODE,\n                    MAINCATEGORY, REBATE, ITEMNAMEARA, DESCRIPTION,\n                    PROPERTY, ORIGIN, QUANTITYLIMIT, PACKING,\n                    MINISTRYFACTOR, MINISTRYUNIT, VATPERCENT,\n                    SALESACCOUNT, PURCHASEACCOUNT, INVENTORYACCOUNT, COGSACCOUNT,\n                    ITEMFLAG, CREATIONFLAG\n                ) VALUES (\n                    :loc, :icode, 0, :item_name, :manufacturer_id,\n                    0, 0, 0, :base_uom,\n                    :cost_price, :retail_price, :wholesale_price, :third_price, :branch_price,\n                    0, 0, 0, 'N',\n                    '', 0, 0,\n                    0, 0, '', '',\n                    0, 0, 0, '',\n                    '', '', 0,\n                    '', '', '', '',\n                    'Y', 'B'\n                )\n                ", {'loc': loc, 'icode': icode, 'item_name': nm, 'manufacturer_id': (manufacturer_id or '').strip(), 'base_uom': uom, 'cost_price': float(cost_price or 0), 'retail_price': float(retail_price or 0), 'wholesale_price': float(wholesale_price or 0), 'third_price': float(third_price or 0), 'branch_price': float(branch_price or 0)})
            conn.commit()
            return 'inserted'

def ensure_itemmaster_account_columns() -> None:
    """Ensure ITEMMASTER has account columns; backfill defaults only when columns were missing."""
    global _ITEMMASTER_ACCOUNT_COLUMNS_READY
    if _ITEMMASTER_ACCOUNT_COLUMNS_READY:
        return
    item_table = dbm._detect_table(['ITEMMASTER', 'itemmaster'])
    if not item_table:
        _ITEMMASTER_ACCOUNT_COLUMNS_READY = True
        return
    defaults = {'SALESACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('customer_sales') or 4100), 'PURCHASEACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('supplier_purchase') or 5001), 'INVENTORYACCOUNT': 1300, 'COGSACCOUNT': 5100}
    cols = {c.upper() for c in (dbm._get_table_columns(item_table) or [])}
    missing = [col for col in defaults if col not in cols]
    if not missing:
        _ITEMMASTER_ACCOUNT_COLUMNS_READY = True
        return
    with dbm._get_connection() as conn:
        with conn.cursor() as cur:
            for col in missing:
                cur.execute(f'ALTER TABLE {item_table} ADD {col} NUMBER(10)')
            for col in missing:
                cur.execute(
                    f"""
                    UPDATE {item_table}
                    SET {col} = :v
                    WHERE {col} IS NULL OR NVL({col}, 0) = 0
                    """,
                    {'v': defaults[col]},
                )
        conn.commit()
    dbm._TABLE_COLUMNS_CACHE.pop(item_table.upper(), None)
    _ITEMMASTER_ACCOUNT_COLUMNS_READY = True


def _itemmaster_account_defaults() -> Dict[str, int]:
    return {
        'SALESACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('customer_sales') or 4100),
        'PURCHASEACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('supplier_purchase') or 5001),
        'INVENTORYACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('inventory_asset') or 1300),
        'COGSACCOUNT': int(dbm.DEFAULT_PARTY_ACCOUNTS.get('cogs') or 5100),
    }


def apply_itemmaster_account_defaults_to_item_data(
    item_data: Dict[str, Any],
    existing_item: Optional[Dict[str, Any]] = None,
) -> None:
    """Fill sales/purchase/inventory/cogs on ``item_data`` when blank, zero, or not provided."""
    defaults = _itemmaster_account_defaults()
    fields = (
        ('sales_account', 'SALESACCOUNT', 'SALES_ACCOUNT'),
        ('purchase_account', 'PURCHASEACCOUNT', 'PURCHASE_ACCOUNT'),
        ('inventory_account', 'INVENTORYACCOUNT', 'INVENTORY_ACCOUNT'),
        ('cogs_account', 'COGSACCOUNT', 'COGS_ACCOUNT'),
    )

    def _positive_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        text = str(val).strip()
        if not text or text == '0':
            return None
        if ' - ' in text:
            text = text.split(' - ', 1)[0].strip()
        try:
            n = int(float(text))
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    for item_key, db_col, alt_key in fields:
        val = _positive_int(item_data.get(item_key))
        if val is None and existing_item:
            for ek in (item_key, alt_key, db_col, db_col.lower()):
                val = _positive_int(existing_item.get(ek))
                if val is not None:
                    break
        if val is None:
            val = int(defaults.get(db_col) or 0)
        item_data[item_key] = val


def _itemmaster_missing_account_condition(cols: Set[str], alias: str = '') -> str:
    prefix = f'{alias}.' if alias else ''
    parts: List[str] = []
    for col in _itemmaster_account_defaults():
        if col in cols:
            parts.append(
                f"({prefix}{col} IS NULL OR LENGTH(TRIM(TO_CHAR({prefix}{col}))) = 0 "
                f"OR LENGTH(TRIM(TO_CHAR({prefix}{col}))) IS NULL OR TRIM(TO_CHAR({prefix}{col})) = '0')"
            )
    return ' OR '.join(parts) if parts else '1 = 0'


def count_itemmaster_missing_accounts(location_code: int) -> int:
    """Count ITEMMASTER rows where any account column is blank/zero."""
    ensure_itemmaster_account_columns()
    item_table = dbm._detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    if not dbm._table_exists(item_table):
        return 0
    cols = {c.upper() for c in (dbm._get_table_columns(item_table) or [])}
    condition = _itemmaster_missing_account_condition(cols, 'im')
    params: Dict[str, Any] = {}
    where = [condition]
    if 'LOCATIONCODE' in cols:
        where.append('im.LOCATIONCODE = :loc')
        params['loc'] = int(location_code)
    rows = dbm._safe_rows(
        f"SELECT COUNT(*) AS cnt FROM {item_table} im WHERE {' AND '.join(f'({w})' for w in where)}",
        params,
    )
    try:
        return int((rows or [{}])[0].get('cnt') or 0)
    except (TypeError, ValueError):
        return 0


def bulk_update_itemmaster_missing_accounts_batch(
    location_code: int,
    *,
    limit: int = 250,
) -> Dict[str, Any]:
    """Fill missing ITEMMASTER account columns with defaults without changing existing values."""
    ensure_itemmaster_account_columns()
    item_table = dbm._detect_table(['ITEMMASTER', 'itemmaster']) or 'ITEMMASTER'
    if not dbm._table_exists(item_table):
        return {'processed': 0, 'updated': 0, 'remaining': 0, 'done': True, 'errors': ['ITEMMASTER not found.']}
    cols = {c.upper() for c in (dbm._get_table_columns(item_table) or [])}
    defaults = _itemmaster_account_defaults()
    acct_cols = [col for col in defaults if col in cols]
    if not acct_cols:
        return {'processed': 0, 'updated': 0, 'remaining': 0, 'done': True, 'errors': ['ITEMMASTER account columns are not available.']}
    condition = _itemmaster_missing_account_condition(cols, 'im')
    update_condition = _itemmaster_missing_account_condition(cols)
    lim = max(1, min(int(limit or 250), 1000))
    params: Dict[str, Any] = {'lim': lim}
    where = [condition]
    if 'LOCATIONCODE' in cols:
        where.append('im.LOCATIONCODE = :loc')
        params['loc'] = int(location_code)
    where_sql = ' AND '.join(f'({w})' for w in where)
    order_col = 'ITEMCODE' if 'ITEMCODE' in cols else 'ROWID'
    updated = 0
    try:
        with dbm._get_connection() as conn:
            with conn.cursor() as cur:
                sets: List[str] = []
                upd: Dict[str, Any] = dict(params)
                for col in acct_cols:
                    sets.append(
                        f"{col} = CASE WHEN {col} IS NULL OR LENGTH(TRIM(TO_CHAR({col}))) = 0 OR LENGTH(TRIM(TO_CHAR({col}))) IS NULL OR TRIM(TO_CHAR({col})) = '0' THEN :{col.lower()} ELSE {col} END"
                    )
                    upd[col.lower()] = defaults[col]
                cur.execute(
                    f"""
                    UPDATE {item_table}
                    SET {', '.join(sets)}
                    WHERE ROWID IN (
                        SELECT rid
                        FROM (
                            SELECT im.ROWID AS rid,
                                   ROW_NUMBER() OVER (ORDER BY im.{order_col}) AS rn
                            FROM {item_table} im
                            WHERE {where_sql}
                        )
                        WHERE rn <= :lim
                    )
                      AND ({update_condition})
                    """,
                    upd,
                )
                updated = int(cur.rowcount or 0)
            conn.commit()
    except Exception as ex:
        return {
            'processed': updated,
            'updated': updated,
            'remaining': count_itemmaster_missing_accounts(location_code),
            'done': False,
            'errors': [str(ex)],
        }
    remaining = count_itemmaster_missing_accounts(location_code)
    return {
        'processed': updated,
        'updated': updated,
        'remaining': remaining,
        'done': remaining <= 0 or updated <= 0,
        'defaults': defaults,
        'errors': [],
    }

def save_item(
    item_data: Dict[str, Any],
    is_new: bool = True,
    *,
    conn: Optional[Any] = None,
    item_cols_cache: Optional[Dict[str, Set[str]]] = None,
) -> Any:
    """Save item master data. When ``conn`` is set, runs on that connection without committing."""
    if conn is None:
        ensure_itemmaster_account_columns()
    try:
        dbm.ensure_itemmaster_inventory_extension_columns()
    except Exception:
        pass
    if item_cols_cache is not None:
        item_cols_cache.pop('ITEMMASTER', None)
    location_code = item_data.get('location_code')
    item_code = item_data.get('item_code')

    def _num_or_zero(value: Any) -> float:
        """Normalize numeric bind values to avoid ORA-01722."""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        if not text:
            return 0
        if ' - ' in text:
            text = text.split(' - ', 1)[0].strip()
        try:
            if '.' in text:
                return float(text)
            return int(text)
        except (ValueError, TypeError):
            return 0

    def _num_or_none(value: Any) -> Any:
        """Normalize optional numeric bind values; keep empty as NULL."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if ' - ' in text:
            text = text.split(' - ', 1)[0].strip()
        try:
            if '.' in text:
                return float(text)
            return int(text)
        except (ValueError, TypeError):
            return None
    if is_new:
        query = "\n            INSERT INTO ITEMMASTER (\n                LOCATIONCODE, ITEMCODE, CATEGORYCODE, ITEMNAME, MANUFACTURERID,\n                BRANDCODE, SIZECODE, COLORCODE, BASEUOM,\n                COSTPRICE, RETAILPRICE, WHOLESALEPRICE, THIRDPRICE, BRANCHPRICE,\n                MAXIMUMLEVEL, REORDERLEVEL, CURRENTSTOCK, DISCOUNTFLAG,\n                COMPANYCODE, SUPCODE, DEPARTMENTCODE,\n                MAINCATEGORY, REBATE, ITEMNAMEARA, DESCRIPTION,\n                PROPERTY, ORIGIN, QUANTITYLIMIT, PACKING,\n                MINISTRYFACTOR, MINISTRYUNIT, VATPERCENT,\n                SALESACCOUNT, PURCHASEACCOUNT, INVENTORYACCOUNT, COGSACCOUNT,\n                ITEMFLAG, CREATIONFLAG\n            ) VALUES (\n                :location_code, :item_code, :category_code, :item_name, :manufacturer_id,\n                :brand_code, :size_code, :color_code, :base_uom,\n                :cost_price, :retail_price, :wholesale_price, :third_price, :branch_price,\n                :maximum_level, :reorder_level, 0, :discount_flag,\n                :company_code, :sup_code, :department_code,\n                :main_category, :rebate, :item_name_ara, :description,\n                :property, :origin, :quantity_limit, :packing,\n                :ministry_factor, :ministry_unit, :vat_percent,\n                :sales_account, :purchase_account, :inventory_account, :cogs_account,\n                'Y', 'B'\n            )\n        "
    else:
        query = '\n            UPDATE ITEMMASTER SET\n                CATEGORYCODE = :category_code,\n                ITEMNAME = :item_name,\n                MANUFACTURERID = :manufacturer_id,\n                BRANDCODE = :brand_code,\n                SIZECODE = :size_code,\n                COLORCODE = :color_code,\n                BASEUOM = :base_uom,\n                COSTPRICE = :cost_price,\n                RETAILPRICE = :retail_price,\n                WHOLESALEPRICE = :wholesale_price,\n                THIRDPRICE = :third_price,\n                BRANCHPRICE = :branch_price,\n                MAXIMUMLEVEL = :maximum_level,\n                REORDERLEVEL = :reorder_level,\n                DISCOUNTFLAG = :discount_flag,\n                COMPANYCODE = :company_code,\n                SUPCODE = :sup_code,\n\n                DEPARTMENTCODE = :department_code,\n                MAINCATEGORY = :main_category,\n                REBATE = :rebate,\n                ITEMNAMEARA = :item_name_ara,\n                DESCRIPTION = :description,\n                PROPERTY = :property,\n                ORIGIN = :origin,\n                QUANTITYLIMIT = :quantity_limit,\n                PACKING = :packing,\n                MINISTRYFACTOR = :ministry_factor,\n                MINISTRYUNIT = :ministry_unit,\n                VATPERCENT = :vat_percent,\n                SALESACCOUNT = :sales_account,\n                PURCHASEACCOUNT = :purchase_account,\n                INVENTORYACCOUNT = :inventory_account,\n                COGSACCOUNT = :cogs_account,\n                ITEMFLAG = :item_flag\n            WHERE ITEMCODE = :item_code\n            AND LOCATIONCODE = :location_code\n        '
    params = {'location_code': _num_or_zero(location_code), 'item_code': _num_or_zero(item_code), 'category_code': _num_or_zero(item_data.get('category_code')), 'item_name': _clip_itemmaster_item_name(item_data.get('item_name', '')), 'manufacturer_id': item_data.get('manufacturer_id', ''), 'brand_code': _num_or_zero(item_data.get('brand_code')), 'size_code': _num_or_zero(item_data.get('size_code')), 'color_code': _num_or_zero(item_data.get('color_code')), 'base_uom': item_data.get('base_uom', ''), 'cost_price': _num_or_zero(item_data.get('cost_price')), 'retail_price': _num_or_zero(item_data.get('retail_price')), 'wholesale_price': _num_or_zero(item_data.get('wholesale_price')), 'third_price': _num_or_zero(item_data.get('third_price')), 'branch_price': _num_or_zero(item_data.get('branch_price')), 'maximum_level': _num_or_zero(item_data.get('maximum_level')), 'reorder_level': _num_or_zero(item_data.get('reorder_level')), 'discount_flag': item_data.get('discount_flag', 'N'), 'item_flag': 'N' if str(item_data.get('item_flag') or '').strip().upper() == 'N' else 'Y', 'company_code': _num_or_none(item_data.get('company_code')), 'sup_code': _num_or_zero(item_data.get('sup_code')), 'department_code': _num_or_zero(item_data.get('department_code')), 'main_category': _num_or_zero(item_data.get('main_category')), 'rebate': _num_or_zero(item_data.get('rebate')), 'item_name_ara': item_data.get('item_name_ara', ''), 'description': item_data.get('description', ''), 'property': _num_or_zero(item_data.get('property_code') or item_data.get('property')), 'origin': _num_or_zero(item_data.get('origin_code') or item_data.get('origin')), 'quantity_limit': _num_or_zero(item_data.get('quantity_limit')), 'packing': item_data.get('packing', ''), 'ministry_factor': _num_or_zero(item_data.get('ministry_factor')), 'ministry_unit': item_data.get('ministry_unit', ''), 'vat_percent': _num_or_zero(item_data.get('vat_percent')), 'sales_account': _num_or_zero(item_data.get('sales_account')), 'purchase_account': _num_or_zero(item_data.get('purchase_account')), 'inventory_account': _num_or_zero(item_data.get('inventory_account')), 'cogs_account': _num_or_zero(item_data.get('cogs_account'))}

    def _item_cols_for_cursor(cur: Any) -> Set[str]:
        if item_cols_cache is not None:
            cached = item_cols_cache.get('ITEMMASTER')
            if cached is not None:
                return cached
        cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
        cols = {str(r[0]).upper() for r in cur.fetchall() or []}
        if item_cols_cache is not None:
            item_cols_cache['ITEMMASTER'] = cols
        return cols

    def _persist(cur: Any) -> Any:
        cur.execute(query, _cx_oracle_named_binds(query, params))
        loc_i = int(_num_or_zero(location_code))
        ic_i = int(_num_or_zero(item_code))
        item_cols = _item_cols_for_cursor(cur)
        wh_id_val: Optional[int] = None
        raw_wh = item_data.get('default_warehouse_id')
        if raw_wh is not None and str(raw_wh).strip() != '':
            try:
                wh_id_val = int(float(str(raw_wh).strip()))
            except (TypeError, ValueError):
                wh_id_val = None
        if 'DEFAULT_WAREHOUSE_ID' in item_cols:
            _st_sql = 'UPDATE ITEMMASTER SET DEFAULT_WAREHOUSE_ID = :wh_id WHERE ITEMCODE = :item_code AND LOCATIONCODE = :location_code'
            cur.execute(_st_sql, _cx_oracle_named_binds(_st_sql, {'wh_id': wh_id_val, 'item_code': ic_i, 'location_code': loc_i}))
        try:
            if 'RAWABICODE' in item_cols:
                cur.execute('\n                            UPDATE ITEMMASTER\n                            SET RAWABICODE = :item_code\n                            WHERE ITEMCODE = :item_code\n                              AND LOCATIONCODE = :location_code\n                            ', {'item_code': ic_i, 'location_code': loc_i})
            _itemmaster_sync_ownproduct_column(cur, item_cols, item_data, ic_i, loc_i)
        except Exception as exc:
            logging.getLogger(__name__).warning('save_item optional column sync failed: %s', exc)
        return item_code
    try:
        if conn is not None:
            with conn.cursor() as cur:
                return _persist(cur)
        with dbm._get_connection() as conn2:
            with conn2.cursor() as cur:
                _persist(cur)
            conn2.commit()
            return item_code
    except Exception as e:
        print(f'[ERROR save_item] {e}')
        import traceback
        traceback.print_exc()
        raise

def save_item_alternate_uom(data: Dict[str, Any], *, conn: Optional[Any]=None, uom_db_key: Optional[str]=None) -> Tuple[bool, Optional[str]]:
    """Insert item alternate UOM mapping with validation"""
    ensure_itemalternateuommap_extension_columns(conn=conn)
    params = {'location_code': data.get('location_code'), 'item_code': data.get('item_code'), 'slno': data.get('slno'), 'alternate_uom_code': data.get('alternate_uom_code'), 'manufacturer_id': data.get('manufacturer_id'), 'conversion_factor': data.get('conversion_factor') or 0, 'cost_price': data.get('cost_price') or 0, 'wholesale_price': data.get('wholesale_price') or 0, 'retail_price': data.get('retail_price') or 0, 'third_price': data.get('third_price') or 0, 'branch_price': data.get('branch_price') or 0}
    params['alternate_uom_code'] = _normalize_alternate_uom_code(params.get('alternate_uom_code'))
    alt_uom = str(params.get('alternate_uom_code') or '').strip()
    alt_barcode = str(params.get('manufacturer_id') or '').strip()
    if not alt_uom:
        return (False, 'Alternate UOM code is required.')

    def _bind(*keys: str) -> Dict[str, Any]:
        return {k: params.get(k) for k in keys}

    def _append_extension_columns_to_update(set_parts: List[str]) -> None:
        has_desc, has_base = _itemalternateuommap_has_extension_columns()
        if has_desc:
            set_parts.append('DESCRIPTION = :description')
        if has_base:
            set_parts.append('IS_BASE = :is_base')

    def _extension_params_from_data() -> None:
        has_desc, has_base = _itemalternateuommap_has_extension_columns()
        if has_desc:
            params['description'] = str(data.get('description') or '')[:500]
        if has_base:
            params['is_base'] = 'Y' if _alternate_row_is_base_flag(data) else 'N'

    try:
        try:
            loc_i = int(float(str(params.get('location_code') or '').strip().split(' - ', 1)[0]))
            icode_i = int(float(str(params.get('item_code') or '').strip().split(' - ', 1)[0]))
        except (TypeError, ValueError):
            return (False, 'Invalid location or item code for alternate UOM.')
        if loc_i <= 0 or icode_i <= 0:
            return (False, 'Invalid location or item code for alternate UOM.')
        params['location_code'] = loc_i
        params['item_code'] = icode_i
        base_uom = _normalize_alternate_uom_code(data.get('base_uom'))
        if _alternate_uom_is_itemmaster_mirror(data, base_uom, alt_uom, params.get('conversion_factor'), alt_barcode):
            master_bc = str(data.get('item_manufacturer_id') or data.get('manufacturer_id') or icode_i).strip()
            params['alternate_uom_code'] = base_uom or alt_uom
            params['manufacturer_id'] = master_bc
            params['conversion_factor'] = 1
            alt_uom = params['alternate_uom_code']
            alt_barcode = master_bc
            master_cost = _itemmaster_price_num(data.get('cost_price'))
            if master_cost or data.get('cost_price') is not None:
                params['cost_price'] = round(float(params['conversion_factor'] or 1) * master_cost, 3)
            for k, dk in (
                ('wholesale_price', 'wholesale_price'),
                ('retail_price', 'retail_price'),
                ('third_price', 'third_price'),
                ('branch_price', 'branch_price'),
            ):
                if data.get(dk) is not None:
                    params[k] = _itemmaster_price_num(data.get(dk))
        _extension_params_from_data()
        if base_uom and base_uom.upper() == alt_uom.upper() and (not _alternate_uom_is_itemmaster_mirror(data, base_uom, alt_uom, params.get('conversion_factor'), alt_barcode)):
            return (False, 'Alternate UOM cannot match Base UOM. Please use another UOM.')
        _uom_db_key_arg = (str(uom_db_key).strip() or None) if uom_db_key is not None else None
        if not dbm.uom_code_exists_for_location(alt_uom, loc_i, _uom_db_key_arg):
            return (False, 'This alternate UOM is not on file for the current branch in Unit of measurement. If your database stores units per location, add this code under Inventory → Unit of measurement for this branch (it may exist for another location only).')

        def _run(cur: Any) -> Tuple[bool, Optional[str]]:
            slno_raw = str(params.get('slno') or '').strip()
            target_slno: Optional[int] = None
            if slno_raw:
                try:
                    cand_sl = int(slno_raw)
                except (ValueError, TypeError):
                    return (False, 'Invalid alternate row.')
                hit_sl = _cursor_safe_rows(cur, '\n                SELECT SLNO AS slno\n                FROM ITEMALTERNATEUOMMAP\n                WHERE LOCATIONCODE = :location_code\n                  AND ITEMCODE = :item_code\n                  AND SLNO = :cand_sl\n                ', {**_bind('location_code', 'item_code'), 'cand_sl': cand_sl})
                if hit_sl:
                    _rs = hit_sl[0].get('slno')
                    if _rs is not None:
                        target_slno = int(_rs)
                else:
                    hit_u = _cursor_safe_rows(cur, '\n                    SELECT SLNO AS slno FROM (\n                        SELECT SLNO FROM ITEMALTERNATEUOMMAP\n                        WHERE LOCATIONCODE = :location_code\n                          AND ITEMCODE = :item_code\n                          AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                        ORDER BY SLNO\n                    ) WHERE ROWNUM <= 1\n                    ', _bind('location_code', 'item_code', 'alternate_uom_code'))
                    if hit_u:
                        _ru = hit_u[0].get('slno')
                        if _ru is not None:
                            target_slno = int(_ru)
            if target_slno is not None:
                params['slno'] = target_slno
                dup_uom_rows = _cursor_safe_rows(cur, '\n                SELECT SLNO\n                FROM ITEMALTERNATEUOMMAP\n                WHERE LOCATIONCODE = :location_code\n                  AND ITEMCODE = :item_code\n                  AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                  AND SLNO <> :slno\n                ', _bind('location_code', 'item_code', 'alternate_uom_code', 'slno'))
                if dup_uom_rows:
                    return (False, 'Alternate UOM already exists for this item. Please use another UOM.')
                if alt_barcode:
                    pref_sl = _preferred_alternate_slno_cur(
                        cur, loc_i, icode_i, manufacturer_id=alt_barcode, alternate_uom_code=alt_uom,
                    )
                    if pref_sl is not None:
                        params['slno'] = pref_sl
                    barcode_in_master_rows = _cursor_safe_rows(cur, '\n                    SELECT ITEMCODE\n                    FROM ITEMMASTER\n                    WHERE LOCATIONCODE = :location_code\n                      AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                      AND ITEMCODE <> :item_code\n                    ', _bind('location_code', 'manufacturer_id', 'item_code'))
                    if barcode_in_master_rows:
                        return (False, 'Barcode already exists on another item in Item Master. Please use another barcode.')
                set_parts = [
                    'ALTERNATEUOMCODE = :alternate_uom_code',
                    'MANUFACTURERID = :manufacturer_id',
                    'CONVERSIONFACTOR = :conversion_factor',
                    'COSTPRICE = :cost_price',
                    'WHOLESALEPRICE = :wholesale_price',
                    'RETAILPRICE = :retail_price',
                    'THIRDPRICE = :third_price',
                    'BRANCHPRICE = :branch_price',
                ]
                _append_extension_columns_to_update(set_parts)
                if str(params.get('is_base') or '').upper() == 'Y':
                    cur.execute(
                        """
                        UPDATE ITEMALTERNATEUOMMAP SET IS_BASE = 'N'
                        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
                          AND NVL(IS_BASE, 'N') = 'Y' AND SLNO <> :slno
                        """,
                        {'location_code': loc_i, 'item_code': icode_i, 'slno': int(params['slno'])},
                    )
                update_query = f"""
                UPDATE ITEMALTERNATEUOMMAP
                SET {', '.join(set_parts)}
                WHERE LOCATIONCODE = :location_code
                AND ITEMCODE = :item_code
                AND SLNO = :slno
            """
                cur.execute(update_query, _cx_oracle_named_binds(update_query, params))
                rc_upd = getattr(cur, 'rowcount', None)
                if rc_upd == 0:
                    return (False, 'Alternate UOM update failed.')
                return (True, None)
            check_query = '\n            SELECT SLNO AS slno\n            FROM ITEMALTERNATEUOMMAP\n            WHERE LOCATIONCODE = :location_code\n            AND ITEMCODE = :item_code\n            AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n        '
            rows = _cursor_safe_rows(cur, check_query, _bind('location_code', 'item_code', 'alternate_uom_code'))
            if rows:
                _ru = rows[0].get('slno')
                if _ru is not None:
                    params['slno'] = int(_ru)
                    dup_uom_rows = _cursor_safe_rows(cur, '\n                SELECT SLNO\n                FROM ITEMALTERNATEUOMMAP\n                WHERE LOCATIONCODE = :location_code\n                  AND ITEMCODE = :item_code\n                  AND UPPER(TRIM(ALTERNATEUOMCODE)) = UPPER(TRIM(:alternate_uom_code))\n                  AND SLNO <> :slno\n                ', _bind('location_code', 'item_code', 'alternate_uom_code', 'slno'))
                    if dup_uom_rows:
                        return (False, 'Alternate UOM already exists for this item. Please use another UOM.')
                    if alt_barcode:
                        pref_sl2 = _preferred_alternate_slno_cur(
                            cur, loc_i, icode_i, manufacturer_id=alt_barcode, alternate_uom_code=alt_uom,
                        )
                        if pref_sl2 is not None:
                            params['slno'] = pref_sl2
                        barcode_in_master_rows = _cursor_safe_rows(cur, '\n                    SELECT ITEMCODE\n                    FROM ITEMMASTER\n                    WHERE LOCATIONCODE = :location_code\n                      AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                      AND ITEMCODE <> :item_code\n                    ', _bind('location_code', 'manufacturer_id', 'item_code'))
                        if barcode_in_master_rows:
                            return (False, 'Barcode already exists on another item in Item Master. Please use another barcode.')
                    set_parts = [
                        'ALTERNATEUOMCODE = :alternate_uom_code',
                        'MANUFACTURERID = :manufacturer_id',
                        'CONVERSIONFACTOR = :conversion_factor',
                        'COSTPRICE = :cost_price',
                        'WHOLESALEPRICE = :wholesale_price',
                        'RETAILPRICE = :retail_price',
                        'THIRDPRICE = :third_price',
                        'BRANCHPRICE = :branch_price',
                    ]
                    _append_extension_columns_to_update(set_parts)
                    if str(params.get('is_base') or '').upper() == 'Y':
                        cur.execute(
                            """
                        UPDATE ITEMALTERNATEUOMMAP SET IS_BASE = 'N'
                        WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
                          AND NVL(IS_BASE, 'N') = 'Y' AND SLNO <> :slno
                        """,
                            {'location_code': loc_i, 'item_code': icode_i, 'slno': int(params['slno'])},
                        )
                    update_query = f"""
                UPDATE ITEMALTERNATEUOMMAP
                SET {', '.join(set_parts)}
                WHERE LOCATIONCODE = :location_code
                AND ITEMCODE = :item_code
                AND SLNO = :slno
            """
                    cur.execute(update_query, _cx_oracle_named_binds(update_query, params))
                    rc_upd = getattr(cur, 'rowcount', None)
                    if rc_upd == 0:
                        return (False, 'Alternate UOM update failed.')
                    return (True, None)
            if alt_barcode:
                pref_sl = _preferred_alternate_slno_cur(
                    cur, loc_i, icode_i, manufacturer_id=alt_barcode, alternate_uom_code=alt_uom,
                )
                if pref_sl is not None:
                    params['slno'] = pref_sl
                    set_parts = [
                        'ALTERNATEUOMCODE = :alternate_uom_code',
                        'MANUFACTURERID = :manufacturer_id',
                        'CONVERSIONFACTOR = :conversion_factor',
                        'COSTPRICE = :cost_price',
                        'WHOLESALEPRICE = :wholesale_price',
                        'RETAILPRICE = :retail_price',
                        'THIRDPRICE = :third_price',
                        'BRANCHPRICE = :branch_price',
                    ]
                    _append_extension_columns_to_update(set_parts)
                    if str(params.get('is_base') or '').upper() == 'Y':
                        cur.execute(
                            """
                            UPDATE ITEMALTERNATEUOMMAP SET IS_BASE = 'N'
                            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
                              AND NVL(IS_BASE, 'N') = 'Y' AND SLNO <> :slno
                            """,
                            {'location_code': loc_i, 'item_code': icode_i, 'slno': int(params['slno'])},
                        )
                    update_query = f"""
                        UPDATE ITEMALTERNATEUOMMAP
                        SET {', '.join(set_parts)}
                        WHERE LOCATIONCODE = :location_code
                          AND ITEMCODE = :item_code AND SLNO = :slno
                    """
                    cur.execute(update_query, _cx_oracle_named_binds(update_query, params))
                    return (True, None)
                barcode_in_master_rows = _cursor_safe_rows(cur, '\n                SELECT ITEMCODE\n                FROM ITEMMASTER\n                WHERE LOCATIONCODE = :location_code\n                  AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:manufacturer_id))\n                  AND ITEMCODE <> :item_code\n                ', _bind('location_code', 'manufacturer_id', 'item_code'))
                if barcode_in_master_rows:
                    return (False, 'Barcode already exists on another item in Item Master. Please use another barcode.')
                alt_other_ic = _alternate_barcode_owner_item_code_cur(cur, loc_i, alt_barcode)
                if alt_other_ic is not None and alt_other_ic != icode_i:
                    return (False, 'Barcode already exists on another item (alternate UOM). Please use another barcode.')
            params['slno'] = _next_itemalternate_slno_cursor(cur, int(params['location_code']), int(params['item_code']))
            has_desc, has_base = _itemalternateuommap_has_extension_columns()
            ins_cols = [
                'LOCATIONCODE', 'SLNO', 'ITEMCODE', 'ALTERNATEUOMCODE', 'MANUFACTURERID',
                'CONVERSIONFACTOR', 'COSTPRICE', 'WHOLESALEPRICE', 'RETAILPRICE', 'THIRDPRICE', 'BRANCHPRICE',
            ]
            ins_vals = [
                ':location_code', ':slno', ':item_code', ':alternate_uom_code', ':manufacturer_id',
                ':conversion_factor', ':cost_price', ':wholesale_price', ':retail_price', ':third_price', ':branch_price',
            ]
            if has_desc:
                ins_cols.append('DESCRIPTION')
                ins_vals.append(':description')
            if has_base:
                ins_cols.append('IS_BASE')
                ins_vals.append(':is_base')
            insert_query = f"""
            INSERT INTO ITEMALTERNATEUOMMAP ({', '.join(ins_cols)})
            VALUES ({', '.join(ins_vals)})
        """
            cur.execute(insert_query, _cx_oracle_named_binds(insert_query, params))
            if has_base and str(params.get('is_base') or '').upper() == 'Y':
                _clear_other_base_alternate_rows_cur(cur, loc_i, icode_i, int(params['slno']))
            return (True, None)
        if conn is not None:
            with conn.cursor() as cur:
                return _run(cur)
        with dbm._get_connection() as c:
            try:
                with c.cursor() as cur:
                    ok, err = _run(cur)
                if ok:
                    c.commit()
                else:
                    c.rollback()
                return (ok, err)
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass
                raise
    except Exception as e:
        print(f'[ERROR save_item_alternate_uom] {e}')
        import traceback
        traceback.print_exc()
        err = str(e)
        if 'ORA-01036' in err or '01036' in err:
            return (False, 'Alternate UOM save failed (bind mismatch). Contact support with the log.')
        if 'ORA-00001' in err or '00001' in err:
            return (False, 'Alternate UOM save blocked: duplicate row (database unique constraint).')
        if 'ORA-02291' in err or '02291' in err:
            return (False, 'Database rejected the row (missing parent key). Often the alternate UOM must exist in UNITOFMEASUREMENT for this same LOCATIONCODE. Add it under Inventory → Unit of measurement for this branch, or ask your DBA which foreign key failed.')
        if 'ORA-01400' in err or '01400' in err:
            return (False, 'Alternate UOM save blocked: a required column is empty.')
        if 'ORA-12838' in err or '12838' in err:
            return (False, 'Alternate UOM save failed (Oracle table lock/trigger conflict). Retry the save; if it persists, ask your DBA to check ITEMALTERNATEUOMMAP triggers.')
        if len(err) < 220:
            return (False, f'Failed to save alternate UOM: {err}')
        return (False, 'Failed to save alternate UOM.')


def _next_item_code_on_cursor(cur: Any, location_code: int) -> int:
    rows = _cursor_safe_rows(
        cur,
        """
        SELECT NVL(MAX(ITEMCODE), 999) + 1 AS next_code
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :location_code
        """,
        {'location_code': int(location_code)},
    )
    if rows and rows[0].get('next_code') is not None:
        try:
            return int(float(rows[0]['next_code']))
        except (TypeError, ValueError):
            pass
    return 1000


def _itemmaster_row_exists_on_cursor(cur: Any, location_code: int, item_code: int) -> bool:
    rows = _cursor_safe_rows(
        cur,
        """
        SELECT ITEMCODE AS ic FROM (
            SELECT ITEMCODE FROM ITEMMASTER
            WHERE LOCATIONCODE = :location_code AND ITEMCODE = :item_code
        ) WHERE ROWNUM <= 1
        """,
        {'location_code': int(location_code), 'item_code': int(item_code)},
    )
    return bool(rows)


def _item_barcode_owner_on_cursor(
    cur: Any,
    location_code: int,
    barcode: str,
    *,
    exclude_item_code: Optional[int] = None,
) -> Optional[int]:
    """Return ITEMCODE if barcode exists on ITEMMASTER or ITEMALTERNATEUOMMAP."""
    bc = str(barcode or '').strip()
    if not bc:
        return None
    loc = int(location_code)
    params: Dict[str, Any] = {'loc': loc, 'bc': bc}
    excl_sql = ''
    if exclude_item_code is not None:
        try:
            params['ex_ic'] = int(exclude_item_code)
            excl_sql = ' AND ITEMCODE <> :ex_ic'
        except (TypeError, ValueError):
            pass
    for tbl in ('ITEMALTERNATEUOMMAP', 'ITEMMASTER'):
        if not dbm._table_exists(tbl):
            continue
        q = f"""
            SELECT ITEMCODE AS ic FROM (
                SELECT ITEMCODE FROM {tbl}
                WHERE LOCATIONCODE = :loc
                  AND UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:bc))
                  {excl_sql}
            ) WHERE ROWNUM <= 1
        """
        hit = _cursor_safe_rows(cur, q, params)
        if hit and hit[0].get('ic') is not None:
            try:
                return int(float(hit[0]['ic']))
            except (TypeError, ValueError):
                continue
    return None


def save_grn_quick_item_new(item_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], bool]:
    """GRN quick-create: one ITEMMASTER row + one base ITEMALTERNATEUOMMAP row in a single transaction.

    Re-checks barcode inside the transaction to block duplicate saves (double-click / concurrent POST).
    Returns ``(item_code, error_message, already_existed)``.
    """
    try:
        loc = int(float(str(item_data.get('location_code') or '1').strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        loc = 1
    barcode = str(item_data.get('manufacturer_id') or item_data.get('barcode') or '').strip()
    if not barcode:
        return None, 'Barcode is required.', False

    def _load_existing_after_conflict() -> Optional[str]:
        try:
            with dbm._get_connection() as conn2:
                with conn2.cursor() as cur2:
                    ic = _item_barcode_owner_on_cursor(cur2, loc, barcode)
                    return str(ic) if ic is not None else None
        except Exception:
            return None

    with dbm._get_connection() as conn:
        try:
            with conn.cursor() as cur:
                existing_ic = _item_barcode_owner_on_cursor(cur, loc, barcode)
                if existing_ic is not None:
                    conn.rollback()
                    return str(existing_ic), None, True

                item_code = _next_item_code_on_cursor(cur, loc)
                while _itemmaster_row_exists_on_cursor(cur, loc, item_code):
                    item_code += 1

                payload = dict(item_data)
                payload['location_code'] = loc
                payload['item_code'] = str(item_code)
                payload['manufacturer_id'] = barcode

                saved_code = save_item(payload, True, conn=conn)
                sync_item = dict(payload)
                sync_item['item_code'] = saved_code
                sync_base_alternate_row_from_itemmaster_cur(cur, sync_item)

            conn.commit()
            return str(saved_code).strip(), None, False
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            err = str(exc)
            if 'ORA-00001' in err or '00001' in err:
                existing = _load_existing_after_conflict()
                if existing:
                    return existing, None, True
                return None, 'Duplicate item save blocked (item or barcode already exists).', False
            raise


def save_itemmaster_with_alternate_uoms(item_data: Dict[str, Any], is_new: bool, alternate_uom_payloads: List[Dict[str, Any]]) -> Tuple[Optional[Any], Optional[str]]:
    """Persist ITEMMASTER and ITEMALTERNATEUOMMAP in one tenant DB transaction.

    Returns ``(saved_item_code, None)`` on success, or ``(None, message)`` on validation/logical failure (transaction rolled back).
    """
    ensure_itemmaster_account_columns()
    ensure_itemalternateuommap_extension_columns()
    try:
        dbm.ensure_itemmaster_inventory_extension_columns()
    except Exception:
        pass
    alt_payloads = _alternate_uom_payloads_for_save(item_data, is_new, alternate_uom_payloads)
    base_saved_in_payloads = _alternate_payloads_include_base_mirror(item_data, alt_payloads)
    with dbm._get_connection() as conn:
        try:
            saved_item_code = save_item(item_data, is_new, conn=conn)
            sync_item = dict(item_data)
            sync_item['item_code'] = saved_item_code
            with conn.cursor() as cur:
                for payload in alt_payloads:
                    alt_ok, alt_err = save_item_alternate_uom(payload, conn=conn)
                    if not alt_ok:
                        conn.rollback()
                        return None, alt_err or 'Alternate UOM save failed.'
                if not base_saved_in_payloads:
                    sync_base_alternate_row_from_itemmaster_cur(cur, sync_item, auto_dedupe=False)
            conn.commit()
            return saved_item_code, None
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

def save_itemmaster_with_alternate_uoms_for_tenant(item_data: Dict[str, Any], is_new: bool, alternate_uom_payloads: List[Dict[str, Any]], tenant_id: str) -> Tuple[Optional[Any], Optional[str]]:
    """Like :func:`save_itemmaster_with_alternate_uoms` but targets a specific tenant connection (HO central DB, etc.)."""
    tid = (tenant_id or '').strip()
    ensure_itemmaster_account_columns()
    icode_raw = item_data.get('item_code')
    try:
        item_code_int = int(float(str(icode_raw).strip().split(' - ', 1)[0]))
    except (TypeError, ValueError):
        item_code_int = 0
    if item_code_int <= 0:
        return None, 'Invalid item code.'
    with dbm._get_tenant_connection(tid) as conn:
        try:
            ok = save_item_in_tenant(item_data, is_new, tid, conn=conn)
            if not ok:
                conn.rollback()
                return None, 'Failed to save item master record.'
            alt_payloads = _alternate_uom_payloads_for_save(item_data, is_new, alternate_uom_payloads, uom_db_key=tid)
            for payload in alt_payloads:
                alt_ok, alt_err = save_item_alternate_uom(payload, conn=conn, uom_db_key=tid)
                if not alt_ok:
                    conn.rollback()
                    return None, alt_err or 'Alternate UOM save failed.'
            conn.commit()
            return item_code_int, None
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
