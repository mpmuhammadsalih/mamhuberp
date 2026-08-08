"""HO Item Request — ITEMMASTERTEMP / LOCATIONS persistence (explicit HO tenant).

Not used for branch ``save_item`` or for HQ central ``save_item_in_tenant``;
those have their own entrypoint modules.
"""
from typing import Any, Dict, List, Optional
from nexa_http import session
from db import PRIVILEGED_USERS, _fix_mojibake, _get_tenant_connection, _materialize_db_value, get_user_tenant_id
ITEM_REQUEST_LOCATIONS_TABLE = 'LOCATIONS'

def _safe_int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default

def _effective_tenant_for_request(preferred_tenant: str='') -> str:
    tenant = (preferred_tenant or '').strip()
    if tenant:
        return tenant
    tenant = str(session.get('tenant_id') or '').strip()
    if tenant:
        return tenant
    user = str(session.get('user') or '').strip()
    if user:
        try:
            return str(get_user_tenant_id(user) or '').strip()
        except Exception:
            return ''
    return ''

def _ensure_item_request_temp_tables(tenant_id: str) -> None:
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMMASTERTEMP'")
            has_item_temp = int((cur.fetchone() or [0])[0] or 0) > 0
            if not has_item_temp:
                cur.execute('\n                    CREATE TABLE ITEMMASTERTEMP (\n                        LOCATIONCODE NUMBER(6) NOT NULL,\n                        ITEMCODE NUMBER(10) NOT NULL,\n                        RAWABICODE VARCHAR2(60),\n                        MANUFACTURERID VARCHAR2(60),\n                        ITEMNAME VARCHAR2(200),\n                        ITEMNAMEARA VARCHAR2(200),\n                        DESCRIPTION VARCHAR2(500),\n                        CATEGORYCODE NUMBER(10),\n                        BRANDCODE NUMBER(10),\n                        SIZECODE NUMBER(10),\n                        COLORCODE NUMBER(10),\n                        BASEUOM VARCHAR2(30),\n                        COSTPRICE NUMBER(18,3),\n                        RETAILPRICE NUMBER(18,3),\n                        WHOLESALEPRICE NUMBER(18,3),\n                        THIRDPRICE NUMBER(18,3),\n                        BRANCHPRICE NUMBER(18,3),\n                        MAXIMUMLEVEL NUMBER(18,3),\n                        REORDERLEVEL NUMBER(18,3),\n                        DISCOUNTFLAG CHAR(1),\n                        COMPANYCODE NUMBER(10),\n                        SUPCODE NUMBER(10),\n                        DEPARTMENTCODE NUMBER(10),\n                        MAINCATEGORY NUMBER(10),\n                        REBATE NUMBER(18,3),\n                        PROPERTY NUMBER(10),\n                        ORIGIN NUMBER(10),\n                        QUANTITYLIMIT NUMBER(18,3),\n                        PACKING VARCHAR2(120),\n                        MINISTRYFACTOR NUMBER(18,3),\n                        MINISTRYUNIT VARCHAR2(30),\n                        VATPERCENT NUMBER(10,3),\n                        SALESACCOUNT NUMBER(10),\n                        PURCHASEACCOUNT NUMBER(10),\n                        INVENTORYACCOUNT NUMBER(10),\n                        COGSACCOUNT NUMBER(10),\n                        STORE VARCHAR2(30),\n                        BRANCH VARCHAR2(30),\n                        ITEMFLAG CHAR(1),\n                        CREATIONFLAG CHAR(1),\n                        CREATEDBY VARCHAR2(100),\n                        CREATEDDATE DATE,\n                        UPDATEDBY VARCHAR2(100),\n                        UPDATEDDATE DATE,\n                        CONSTRAINT PK_ITEMMASTERTEMP PRIMARY KEY (LOCATIONCODE, ITEMCODE)\n                    )\n                    ')
            cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTERTEMP'")
            item_temp_cols = {str(r[0]).upper() for r in cur.fetchall() or []}
            required_item_temp_columns = {'BRANCH': 'VARCHAR2(30)', 'STORE': 'VARCHAR2(30)', 'STATUS': 'VARCHAR2(20)', 'RAWABICODE': 'VARCHAR2(60)', 'SALESACCOUNT': 'NUMBER(10)', 'PURCHASEACCOUNT': 'NUMBER(10)', 'INVENTORYACCOUNT': 'NUMBER(10)', 'COGSACCOUNT': 'NUMBER(10)', 'ITEMFLAG': 'CHAR(1)', 'CREATIONFLAG': 'CHAR(1)', 'CREATEDBY': 'VARCHAR2(100)', 'CREATEDDATE': 'DATE', 'UPDATEDBY': 'VARCHAR2(100)', 'UPDATEDDATE': 'DATE', 'REJECTCOMMENT': 'VARCHAR2(500)', 'OWNPRODUCT': 'CHAR(1)'}
            for col_name, col_type in required_item_temp_columns.items():
                if col_name not in item_temp_cols:
                    cur.execute(f'ALTER TABLE ITEMMASTERTEMP ADD {col_name} {col_type}')
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMALTERNATEUOMMAPTEMP'")
            has_alt_temp = int((cur.fetchone() or [0])[0] or 0) > 0
            if not has_alt_temp:
                cur.execute('\n                    CREATE TABLE ITEMALTERNATEUOMMAPTEMP (\n                        LOCATIONCODE NUMBER(6) NOT NULL,\n                        SLNO NUMBER(6) NOT NULL,\n                        ITEMCODE NUMBER(10) NOT NULL,\n                        ALTERNATEUOMCODE VARCHAR2(30),\n                        MANUFACTURERID VARCHAR2(60),\n                        CONVERSIONFACTOR NUMBER(18,3),\n                        COSTPRICE NUMBER(18,3),\n                        WHOLESALEPRICE NUMBER(18,3),\n                        RETAILPRICE NUMBER(18,3),\n                        THIRDPRICE NUMBER(18,3),\n                        BRANCHPRICE NUMBER(18,3),\n                        CONSTRAINT PK_ITEMALTERNATEUOMTEMP PRIMARY KEY (LOCATIONCODE, ITEMCODE, SLNO)\n                    )\n                    ')
        conn.commit()

def _get_location_dbcode_and_dbkey(tenant_id: str, location_code: int):
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                table_candidates = [ITEM_REQUEST_LOCATIONS_TABLE]
                location_table = None
                for tbl in table_candidates:
                    if not tbl:
                        continue
                    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :tbl', {'tbl': tbl})
                    if int((cur.fetchone() or [0])[0] or 0) > 0:
                        location_table = tbl
                        break
                if not location_table:
                    return ('', '')
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :tbl', {'tbl': location_table})
                cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                location_code_col = 'LOCATIONCODE' if 'LOCATIONCODE' in cols else None
                if not location_code_col:
                    return ('', '')
                dbcode_col = 'DBCODE' if 'DBCODE' in cols else 'DBKEY' if 'DBKEY' in cols else None
                dbkey_col = 'DBKEY' if 'DBKEY' in cols else 'DBCODE' if 'DBCODE' in cols else None
                if not (dbcode_col or dbkey_col):
                    return ('', '')
                cur.execute(f'\n                    SELECT TRIM(TO_CHAR({dbcode_col})) AS DBCODE,\n                           TRIM(TO_CHAR({dbkey_col})) AS DBKEY\n                    FROM {location_table}\n                    WHERE {location_code_col} = :loc\n                    ', {'loc': int(location_code)})
                row = cur.fetchone()
                if row:
                    dbcode = str(row[0] or '').strip().upper()
                    dbkey = str(row[1] or '').strip().upper()
                    return (dbcode, dbkey)
    except Exception:
        pass
    return ('', '')

def _get_request_location_rows(tenant_id: str):
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                table_candidates = [ITEM_REQUEST_LOCATIONS_TABLE]
                location_table = None
                for tbl in table_candidates:
                    if not tbl:
                        continue
                    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :tbl', {'tbl': tbl})
                    if int((cur.fetchone() or [0])[0] or 0) > 0:
                        location_table = tbl
                        break
                if not location_table:
                    return []
                cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :tbl', {'tbl': location_table})
                cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                loc_col = 'LOCATIONCODE' if 'LOCATIONCODE' in cols else None
                name_col = 'NAME' if 'NAME' in cols else 'LOCATIONNAME' if 'LOCATIONNAME' in cols else None
                dbocode_col = 'DBCODE' if 'DBCODE' in cols else None
                dbkey_col = 'DBKEY' if 'DBKEY' in cols else None
                if not (loc_col and dbocode_col and dbkey_col):
                    return []
                name_expr = name_col if name_col else "''"
                cur.execute(f'\n                    SELECT TRIM(TO_CHAR({dbocode_col})) AS DBOCODE,\n                           TRIM(TO_CHAR({dbkey_col})) AS DBKEY,\n                           {name_expr} AS NAME,\n                           TRIM(TO_CHAR({loc_col})) AS LOCATIONCODE\n                    FROM {location_table}\n                    WHERE {loc_col} IS NOT NULL\n                      AND {dbocode_col} IS NOT NULL\n                      AND {dbkey_col} IS NOT NULL\n                    ORDER BY {loc_col}\n                    ')
                rows = cur.fetchall() or []
                out = []
                for r in rows:
                    code = str((r[0] if len(r) > 0 else '') or '').strip().upper()
                    if not code:
                        continue
                    out.append({'code': code, 'dbkey': str((r[1] if len(r) > 1 else '') or '').strip().upper(), 'name': str((r[2] if len(r) > 2 else '') or '').strip(), 'locationcode': str((r[3] if len(r) > 3 else '') or '').strip().upper()})
                return out
    except Exception:
        return []

def _get_request_location_row_by_code(tenant_id: str, code_value: str):
    code_clean = str(code_value or '').strip()
    if not code_clean:
        return None
    rows = _get_request_location_rows(tenant_id)
    for row in rows:
        if str(row.get('code') or '').strip().upper() == code_clean.upper():
            return row
    return None

def _get_request_location_row_by_locationcode(tenant_id: str, location_code: str):
    code_clean = str(location_code or '').strip()
    if not code_clean:
        return None
    rows = _get_request_location_rows(tenant_id)
    for row in rows:
        if str(row.get('locationcode') or '').strip().upper() == code_clean.upper():
            return row
    return None

def _coerce_request_location_code(cur, table_name: str, preferred_dbcode: str, fallback_location_code: int):
    cur.execute("\n        SELECT data_type\n        FROM user_tab_columns\n        WHERE table_name = :tbl\n          AND column_name = 'LOCATIONCODE'\n        ", {'tbl': table_name})
    row = cur.fetchone()
    data_type = str((row or [None])[0] or '').upper()
    if 'CHAR' in data_type or 'CLOB' in data_type:
        return str(preferred_dbcode or fallback_location_code or '').strip().upper()
    if preferred_dbcode and str(preferred_dbcode).strip().isdigit():
        return int(str(preferred_dbcode).strip())
    return int(fallback_location_code or 0)

def _get_next_item_request_code_from_temp(tenant_id: str, preferred_dbcode: str, fallback_location_code: int) -> int:
    _ensure_item_request_temp_tables(tenant_id)
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT NVL(MAX(ITEMCODE), 0) + 1 FROM ITEMMASTERTEMP')
            row = cur.fetchone()
            return _safe_int((row or [1])[0], 1) or 1

def _get_item_request_temp_row(tenant_id: str, location_code, item_code: str='', manufacturer_id: str=''):
    code_val = _safe_int(item_code, 0) if str(item_code or '').strip() else 0
    barcode_val = str(manufacturer_id or '').strip()
    where_parts = []
    params = {}
    if location_code not in (None, ''):
        where_parts.append('LOCATIONCODE = :loc')
        params['loc'] = location_code
    if code_val > 0:
        where_parts.append('ITEMCODE = :icode')
        params['icode'] = code_val
    elif barcode_val:
        where_parts.append('UPPER(TRIM(MANUFACTURERID)) = UPPER(TRIM(:barcode))')
        params['barcode'] = barcode_val
    else:
        return None
    where_sql = ' AND '.join(where_parts) if where_parts else '1=1'
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute(f'\n                    SELECT *\n                    FROM ITEMMASTERTEMP\n                    WHERE {where_sql}\n                    ', params)
                row = cur.fetchone()
                if not row:
                    return None
                cols = [str(c[0]).lower() for c in cur.description or []]
                data = {k: _materialize_db_value(v) for k, v in zip(cols, row)}
                if data.get('itemnameara') is not None:
                    data['itemnameara'] = _fix_mojibake(data.get('itemnameara'))
                if data.get('description') is not None:
                    data['description'] = _fix_mojibake(data.get('description'))
                data['sales_account'] = data.get('salesaccount')
                data['purchase_account'] = data.get('purchaseaccount')
                data['inventory_account'] = data.get('inventoryaccount')
                data['cogs_account'] = data.get('cogsaccount')
                return data
    except Exception:
        return None

def _get_item_request_alt_rows(tenant_id: str, location_code, item_code: int):
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute('\n                    SELECT LOCATIONCODE, SLNO, ITEMCODE, ALTERNATEUOMCODE, MANUFACTURERID,\n                           CONVERSIONFACTOR, COSTPRICE, WHOLESALEPRICE, RETAILPRICE, THIRDPRICE, BRANCHPRICE\n                    FROM ITEMALTERNATEUOMMAPTEMP\n                    WHERE LOCATIONCODE = :loc\n                      AND ITEMCODE = :icode\n                    ORDER BY SLNO\n                    ', {'loc': location_code, 'icode': int(item_code)})
                rows = cur.fetchall() or []
                cols = [str(c[0]).lower() for c in cur.description or []]
                return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []

def _item_request_list_branch_filter() -> Optional[str]:
    """Branch DBKEY filter for ITEMMASTERTEMP.BRANCH. None = show all (HO / privileged)."""
    current_user = str(session.get('user') or '').strip()
    current_tenant = _effective_tenant_for_request().upper()
    if current_user.lower() in {u.lower() for u in PRIVILEGED_USERS}:
        return None
    if current_tenant == 'HO':
        return None
    return current_tenant or '__NO_TENANT__'

def _item_request_can_access_temp_row(temp_row: Optional[dict]) -> bool:
    if not temp_row:
        return False
    bf = _item_request_list_branch_filter()
    if bf is None:
        return True
    br = str(temp_row.get('branch') or '').strip().upper()
    return bool(br) and br == str(bf).strip().upper()

def _get_item_request_status_counts(tenant_id: str, branch_filter: Optional[str]=None):
    counts = {'pending': 0, 'approved': 0, 'rejected': 0}
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                where_parts: List[str] = []
                params: Dict[str, Any] = {}
                if branch_filter is not None:
                    where_parts.append("UPPER(NVL(BRANCH,'')) = :br")
                    params['br'] = str(branch_filter).strip().upper()
                where_sql = 'WHERE ' + ' AND '.join(where_parts) if where_parts else ''
                cur.execute(f"\n                    SELECT UPPER(NVL(STATUS, 'PENDING')) AS ST, COUNT(*)\n                    FROM ITEMMASTERTEMP\n                    {where_sql}\n                    GROUP BY UPPER(NVL(STATUS, 'PENDING'))\n                    ", params)
                for st, cnt in cur.fetchall() or []:
                    key = str(st or '').strip().lower()
                    if key in counts:
                        counts[key] = int(cnt or 0)
    except Exception:
        pass
    return counts

def _get_item_request_rows_by_status(tenant_id: str, status_key: str, branch_filter: Optional[str]=None):
    status_key = str(status_key or 'pending').strip().lower()
    status_map = {'pending': 'PENDING', 'approved': 'APPROVED', 'rejected': 'REJECTED'}
    status_val = status_map.get(status_key, 'PENDING')
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                where_parts = ["UPPER(NVL(STATUS, 'PENDING')) = :st"]
                params: Dict[str, Any] = {'st': status_val}
                if branch_filter is not None:
                    where_parts.append("UPPER(NVL(BRANCH,'')) = :br")
                    params['br'] = str(branch_filter).strip().upper()
                where_sql = ' AND '.join(where_parts)
                cur.execute(f"\n                    SELECT\n                        LOCATIONCODE,\n                        ITEMCODE,\n                        MANUFACTURERID,\n                        ITEMNAME,\n                        BRANCH,\n                        UPPER(NVL(STATUS, 'PENDING')) AS STATUS,\n                        CREATEDBY,\n                        CREATEDDATE,\n                        UPDATEDBY,\n                        UPDATEDDATE,\n                        REJECTCOMMENT\n                    FROM ITEMMASTERTEMP\n                    WHERE {where_sql}\n                    ORDER BY NVL(UPDATEDDATE, CREATEDDATE) DESC, ITEMCODE DESC\n                    ", params)
                rows = cur.fetchall() or []
                cols = [str(c[0]).lower() for c in cur.description or []]
                return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []

def _get_item_request_temp_row_by_item_code(tenant_id: str, item_code: int):
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute('\n                    SELECT *\n                    FROM (\n                        SELECT *\n                        FROM ITEMMASTERTEMP\n                        WHERE ITEMCODE = :icode\n                        ORDER BY NVL(UPDATEDDATE, CREATEDDATE) DESC\n                    )\n                    WHERE ROWNUM = 1\n                    ', {'icode': int(item_code)})
                row = cur.fetchone()
                if not row:
                    return None
                cols = [str(c[0]).lower() for c in cur.description or []]
                data = {k: _materialize_db_value(v) for k, v in zip(cols, row)}
                if data.get('itemnameara') is not None:
                    data['itemnameara'] = _fix_mojibake(data.get('itemnameara'))
                if data.get('description') is not None:
                    data['description'] = _fix_mojibake(data.get('description'))
                return data
    except Exception:
        return None
