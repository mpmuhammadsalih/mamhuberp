"""HO Itemmaster Central — tenant-targeted ITEMMASTER persistence and remap.

Use this module from HO central routes only. Branch Item Master uses
``addons.itemmaster.db_branch_item_store``; item requests use ``db_item_request``.
Implementation remains in ``db.py``; this file is the central entrypoint boundary.
"""
from db import check_item_exists_by_rawabicode_for_tenant, get_item_alternate_uom_for_tenant, get_item_alternate_uoms_for_tenant, get_item_by_code_for_tenant, get_item_by_manufacturer_id_for_tenant, get_item_details_by_rawabicode_for_tenant, get_item_rawabicode_for_tenant, get_itemmaster_list_from_tenant, get_next_item_code_for_tenant, remap_itemmaster_to_tenant, save_item_alternate_uom_in_tenant, save_item_in_tenant, save_itemmaster_with_alternate_uoms_for_tenant, _get_tenant_connection
__all__ = ['check_item_exists_by_rawabicode_for_tenant', 'get_item_alternate_uom_for_tenant', 'get_item_alternate_uoms_for_tenant', 'get_item_by_code_for_tenant', 'get_item_by_manufacturer_id_for_tenant', 'get_item_details_by_rawabicode_for_tenant', 'get_item_rawabicode_for_tenant', 'get_itemmaster_list_from_tenant', 'get_next_item_code_for_tenant', 'remap_itemmaster_to_tenant', 'save_item_alternate_uom_in_tenant', 'save_item_in_tenant', 'save_itemmaster_with_alternate_uoms_for_tenant', '_ensure_itemmaster_tempitemcode_column', '_ensure_itemmaster_convert_columns', '_ensure_itemdeleted_table']

def _ensure_itemmaster_tempitemcode_column(tenant_id: str) -> None:
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMMASTER'")
                has_itemmaster = int((cur.fetchone() or [0])[0] or 0) > 0
                if not has_itemmaster:
                    return
                cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'ITEMMASTER' AND column_name = 'TEMPITEMCODE'")
                has_col = int((cur.fetchone() or [0])[0] or 0) > 0
                if not has_col:
                    cur.execute('ALTER TABLE ITEMMASTER ADD TEMPITEMCODE NUMBER(10)')
            conn.commit()
    except Exception:
        pass

def _ensure_itemmaster_convert_columns(tenant_id: str) -> None:
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMMASTER'")
                has_itemmaster = int((cur.fetchone() or [0])[0] or 0) > 0
                if not has_itemmaster:
                    return
                cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMMASTER'")
                cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                required_cols = {'SALESACCOUNT': 'NUMBER(10)', 'PURCHASEACCOUNT': 'NUMBER(10)', 'INVENTORYACCOUNT': 'NUMBER(10)', 'COGSACCOUNT': 'NUMBER(10)'}
                for col_name, col_type in required_cols.items():
                    if col_name not in cols:
                        cur.execute(f'ALTER TABLE ITEMMASTER ADD {col_name} {col_type}')
            conn.commit()
    except Exception:
        pass

def _ensure_itemdeleted_table(tenant_id: str) -> None:
    try:
        with _get_tenant_connection(tenant_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMDELETED'")
                has_table = int((cur.fetchone() or [0])[0] or 0) > 0
                if not has_table:
                    cur.execute('\n                        CREATE TABLE ITEMDELETED (\n                            ITEMCODE NUMBER(10),\n                            ITEMNAME VARCHAR2(200),\n                            DELETEDUSER VARCHAR2(100),\n                            DELETEDDATE DATE\n                        )\n                        ')
                else:
                    cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'ITEMDELETED'")
                    cols = {str(r[0]).upper() for r in cur.fetchall() or []}
                    required_cols = {'ITEMCODE': 'NUMBER(10)', 'ITEMNAME': 'VARCHAR2(200)', 'DELETEDUSER': 'VARCHAR2(100)', 'DELETEDDATE': 'DATE'}
                    for col_name, col_type in required_cols.items():
                        if col_name not in cols:
                            cur.execute(f'ALTER TABLE ITEMDELETED ADD {col_name} {col_type}')
            conn.commit()
    except Exception:
        pass
