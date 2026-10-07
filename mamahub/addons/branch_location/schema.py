"""
Branch / Location master — database objects (tenant connection only).

Uses ``LOCATIONMASTER``-shaped DDL; the effective Oracle table name is taken from:

- Env: ``LOCATIONS_TABLE`` (see ``db.LOCATIONS_TABLE``), default **LOCATIONMASTER**.
- Implemented in: ``db.ensure_location_master_table()`` (DDL + auto-create).
- Helpers: ``db.list_location_master_rows``, ``get_location_master_row``,
  ``insert_location_master_row``, ``update_location_master_row``.
"""
LOCATIONMASTER_DEFAULT_NAME = 'LOCATIONMASTER'
# Legacy / unused on branch screens — still in Oracle table; not shown or updated from UI.
LOCATIONMASTER_UI_HIDDEN_COLUMNS = frozenset({
    'MINUSBILLING', 'PRODUCTION', 'RETURNDETAILS', 'COUPONS', 'LINECOLOR',
    'BASEPRICE', 'CASHLIMIT', 'COUPONAMOUNT', 'FAX', 'ITEMDESCRIPTION',
})
LOCATIONMASTER_COLUMN_ORDER = (
    'LOCATIONCODE', 'LOCATIONNAME', 'ADDRESS', 'TELEPHONE', 'EMAILID', 'MANAGER', 'RESETNO',
    'BASELOCATIONFLAG', 'DBCODE', 'BATCH_TRACKING', 'BIN_TRACKING', 'WAREHOUSE_ENABLE',
    'LOGO_PATH',
)
# Set via branch form file upload; not a free-text field on new/edit screens.
LOCATIONMASTER_LOGO_COLUMN = 'LOGO_PATH'
