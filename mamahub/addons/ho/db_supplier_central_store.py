"""HO Supplier Central tenant-targeted SUPPLIER persistence."""
from typing import Any, Dict, List, Optional
from db import _get_tenant_connection
from master_name_duplicate import find_master_name_duplicate, master_name_duplicate_message
SUPPLIER_TABLE = 'SUPPLIER'
SUPPLIER_COLUMNS = ['LOCATIONCODE', 'SUPPLIERCODE', 'SUPPLIERNAME', 'SUPPLIERTYPE', 'ADDRESS', 'TELEPHONE', 'FAX', 'MOBILE', 'EMAILID', 'CONTACTPERSON', 'SUPPLIERID', 'PAYABLEACCOUNT', 'PURCHASEACCOUNT', 'VATINPUTACCOUNT', 'ADVANCEACCOUNT', 'FLAG', 'SUPPLIERLOCATION', 'SUPREF', 'SUPPLIERCR', 'CREATIONFLAG']

def _rows(cur) -> List[Dict[str, Any]]:
    cols = [str(d[0]).lower() for d in cur.description or []]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def _table_exists(cur, table: str) -> bool:
    cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name = :table_name', {'table_name': table.upper()})
    return int((cur.fetchone() or [0])[0] or 0) > 0

def _columns(cur, table: str) -> List[str]:
    cur.execute('SELECT column_name FROM user_tab_columns WHERE table_name = :table_name', {'table_name': table.upper()})
    return [str(r[0]).upper() for r in cur.fetchall() or []]

def ensure_supplier_table_for_tenant(tenant_id: str) -> None:
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            if not _table_exists(cur, SUPPLIER_TABLE):
                cur.execute("\n                    CREATE TABLE SUPPLIER\n                    (\n                      LOCATIONCODE      NUMBER(2),\n                      SUPPLIERCODE      NUMBER(5),\n                      SUPPLIERNAME      VARCHAR2(40 BYTE) NOT NULL,\n                      SUPPLIERTYPE      VARCHAR2(25 BYTE),\n                      ADDRESS           VARCHAR2(200 BYTE),\n                      TELEPHONE         VARCHAR2(15 BYTE),\n                      FAX               VARCHAR2(15 BYTE),\n                      MOBILE            VARCHAR2(15 BYTE),\n                      EMAILID           VARCHAR2(150 BYTE),\n                      CONTACTPERSON     VARCHAR2(40 BYTE),\n                      SUPPLIERID        CHAR(3 BYTE),\n                      ACCOUNTCODE       NUMBER(10),\n                      PAYABLEACCOUNT    NUMBER(10),\n                      FLAG              CHAR(1 BYTE),\n                      SUPPLIERLOCATION  VARCHAR2(30 BYTE),\n                      SUPREF            VARCHAR2(50 BYTE),\n                      SUPPLIERCR        VARCHAR2(250 BYTE),\n                      PURCHASEACCOUNT   NUMBER(10),\n                      VATINPUTACCOUNT   NUMBER(10),\n                      ADVANCEACCOUNT    NUMBER(10),\n                      CREATIONFLAG      CHAR(1 BYTE) DEFAULT 'B' NOT NULL\n                    )\n                    ")
            cols = set(_columns(cur, SUPPLIER_TABLE))
            for col_name in ('PAYABLEACCOUNT', 'PURCHASEACCOUNT', 'VATINPUTACCOUNT', 'ADVANCEACCOUNT'):
                if col_name not in cols:
                    cur.execute(f'ALTER TABLE SUPPLIER ADD {col_name} NUMBER(10)')
            if 'CREATIONFLAG' not in cols:
                cur.execute("ALTER TABLE SUPPLIER ADD CREATIONFLAG CHAR(1 BYTE) DEFAULT 'B' NOT NULL")
        conn.commit()

def get_next_supplier_code_for_tenant(tenant_id: str, location_code: int) -> int:
    ensure_supplier_table_for_tenant(tenant_id)
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute('\n                SELECT NVL(MAX(SUPPLIERCODE), 0) + 1 AS nextcode\n                FROM SUPPLIER\n                WHERE LOCATIONCODE = :location_code\n                ', {'location_code': location_code})
            row = cur.fetchone()
            return int((row or [1])[0] or 1)

def get_supplier_list_from_tenant(tenant_id: str, *, location_code: int, search: Optional[str]=None, limit: int=500) -> List[Dict[str, Any]]:
    ensure_supplier_table_for_tenant(tenant_id)
    params: Dict[str, Any] = {'location_code': location_code, 'row_limit': max(1, min(int(limit or 500), 2000))}
    where_sql = 'WHERE LOCATIONCODE = :location_code'
    if search and search.strip():
        params['search'] = f'%{search.strip()}%'
        where_sql += ' AND (UPPER(SUPPLIERNAME) LIKE UPPER(:search) OR TO_CHAR(SUPPLIERCODE) LIKE :search)'
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute(f'\n                SELECT *\n                FROM (\n                    SELECT LOCATIONCODE AS locationcode,\n                           SUPPLIERCODE AS suppliercode,\n                           SUPPLIERNAME AS suppliername,\n                           SUPPLIERTYPE AS suppliertype,\n                           CONTACTPERSON AS contactperson,\n                           PAYABLEACCOUNT AS payableaccount,\n                           PURCHASEACCOUNT AS purchaseaccount,\n                           VATINPUTACCOUNT AS vatinputaccount,\n                           ADVANCEACCOUNT AS advanceaccount,\n                           FLAG AS flag\n                    FROM SUPPLIER\n                    {where_sql}\n                    ORDER BY SUPPLIERCODE DESC\n                )\n                WHERE ROWNUM <= :row_limit\n                ', params)
            return _rows(cur)

def get_supplier_by_code_for_tenant(tenant_id: str, location_code: int, supplier_code: int) -> Optional[Dict[str, Any]]:
    ensure_supplier_table_for_tenant(tenant_id)
    cols = ', '.join((f'{c} AS {c.lower()}' for c in SUPPLIER_COLUMNS))
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute(f'\n                SELECT {cols}\n                FROM SUPPLIER\n                WHERE LOCATIONCODE = :location_code\n                  AND SUPPLIERCODE = :supplier_code\n                ', {'location_code': location_code, 'supplier_code': supplier_code})
            rows = _rows(cur)
            return rows[0] if rows else None

def supplier_exists_for_tenant(tenant_id: str, location_code: int, supplier_code: int) -> bool:
    ensure_supplier_table_for_tenant(tenant_id)
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            cur.execute('\n                SELECT COUNT(*) AS cnt\n                FROM SUPPLIER\n                WHERE LOCATIONCODE = :location_code\n                  AND SUPPLIERCODE = :supplier_code\n                ', {'location_code': location_code, 'supplier_code': supplier_code})
            return int((cur.fetchone() or [0])[0] or 0) > 0

def save_supplier_in_tenant(tenant_id: str, *, location_code: int, supplier_code: int, supplier_data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_supplier_table_for_tenant(tenant_id)
    exists = supplier_exists_for_tenant(tenant_id, location_code, supplier_code)
    payload = {'locationcode': location_code, 'suppliercode': supplier_code, 'suppliername': (supplier_data.get('suppliername') or '').strip()[:40], 'suppliertype': (supplier_data.get('suppliertype') or '').strip()[:25] or None, 'address': (supplier_data.get('address') or '').strip()[:200] or None, 'telephone': (supplier_data.get('telephone') or '').strip()[:15] or None, 'fax': (supplier_data.get('fax') or '').strip()[:15] or None, 'mobile': (supplier_data.get('mobile') or '').strip()[:15] or None, 'emailid': (supplier_data.get('emailid') or '').strip()[:150] or None, 'contactperson': (supplier_data.get('contactperson') or '').strip()[:40] or None, 'supplierid': (supplier_data.get('supplierid') or '').strip()[:3] or None, 'payableaccount': supplier_data.get('payableaccount'), 'purchaseaccount': supplier_data.get('purchaseaccount'), 'vatinputaccount': supplier_data.get('vatinputaccount'), 'advanceaccount': supplier_data.get('advanceaccount'), 'flag': (supplier_data.get('flag') or 'Y').strip()[:1] or 'Y', 'supplierlocation': (supplier_data.get('supplierlocation') or '').strip()[:30] or None, 'supref': (supplier_data.get('supref') or '').strip()[:50] or None, 'suppliercr': (supplier_data.get('suppliercr') or '').strip()[:250] or None, 'creationflag': (supplier_data.get('creationflag') or 'B').strip()[:1] or 'B'}
    with _get_tenant_connection(tenant_id) as conn:
        with conn.cursor() as cur:
            actual_cols = set(_columns(cur, SUPPLIER_TABLE))
            if 'SUPPLIERNAME' in actual_cols:
                dup_code = find_master_name_duplicate(
                    cur,
                    table=SUPPLIER_TABLE,
                    name_col='SUPPLIERNAME',
                    name_value=payload.get('suppliername'),
                    loc_col='LOCATIONCODE' if 'LOCATIONCODE' in actual_cols else None,
                    location_code=location_code,
                    code_col='SUPPLIERCODE' if 'SUPPLIERCODE' in actual_cols else None,
                    exclude_code=supplier_code if exists else None,
                )
                if dup_code is not None:
                    raise ValueError(
                        master_name_duplicate_message(
                            'supplier',
                            payload.get('suppliername'),
                            location_code=location_code,
                            existing_code=dup_code,
                        )
                    )
            if exists:
                set_parts = []
                params = {'locationcode': location_code, 'suppliercode': supplier_code}
                for col in SUPPLIER_COLUMNS:
                    if col in ('LOCATIONCODE', 'SUPPLIERCODE') or col not in actual_cols:
                        continue
                    param = col.lower()
                    set_parts.append(f'{col} = :{param}')
                    params[param] = payload.get(param)
                cur.execute(f"\n                    UPDATE SUPPLIER\n                    SET {', '.join(set_parts)}\n                    WHERE LOCATIONCODE = :locationcode\n                      AND SUPPLIERCODE = :suppliercode\n                    ", params)
                action = 'updated'
            else:
                cols = [c for c in SUPPLIER_COLUMNS if c in actual_cols]
                params = {c.lower(): payload.get(c.lower()) for c in cols}
                cur.execute(f"\n                    INSERT INTO SUPPLIER ({', '.join(cols)})\n                    VALUES ({', '.join((':' + c.lower() for c in cols))})\n                    ", params)
                action = 'inserted'
        conn.commit()
    return {'action': action, 'supplier_code': supplier_code}
