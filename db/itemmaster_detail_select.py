"""
Oracle SELECT used for Item Master detail (LBL_* joins). Embedded in-app so opening an item does not require ITEMMASTER_DETAIL_V (or any view) to exist—only the underlying tables.
Keep in sync with sql/oracle/itemmaster_detail_view.sql (view body—without CREATE VIEW).
"""
from __future__ import annotations

import re
from typing import AbstractSet, Set

ITEMMASTER_DETAIL_FROM_SQL = """
FROM ITEMMASTER im
LEFT JOIN CATEGORY cat_m
       ON cat_m.FLAG = 'M' AND cat_m.CODE = im.MAINCATEGORY AND cat_m.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_d
       ON cat_d.FLAG = 'D' AND cat_d.CODE = im.DEPARTMENTCODE AND cat_d.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_c
       ON cat_c.FLAG = 'C' AND cat_c.CODE = im.CATEGORYCODE AND cat_c.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_b
       ON cat_b.FLAG = 'B' AND cat_b.CODE = im.BRANDCODE AND cat_b.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_z
       ON cat_z.FLAG = 'Z' AND cat_z.CODE = im.SIZECODE AND cat_z.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN CATEGORY cat_l
       ON cat_l.FLAG = 'L' AND cat_l.CODE = im.COLORCODE AND cat_l.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN SUPPLIER sup
       ON sup.SUPPLIERCODE = im.SUPCODE AND sup.LOCATIONCODE = im.LOCATIONCODE
LEFT JOIN UNITOFMEASUREMENT u_base
       ON u_base.LOCATIONCODE = im.LOCATIONCODE
      AND TRIM(UPPER(TO_CHAR(u_base.UNITCODE))) = TRIM(UPPER(TO_CHAR(im.BASEUOM)))
LEFT JOIN UNITOFMEASUREMENT u_min
       ON u_min.LOCATIONCODE = im.LOCATIONCODE
      AND TRIM(UPPER(TO_CHAR(u_min.UNITCODE))) = TRIM(UPPER(TO_CHAR(im.MINISTRYUNIT)))
LEFT JOIN TBLITEMPROPERTY prop
       ON prop.CODE = im.PROPERTY
LEFT JOIN TBLITEMORIGIN ori
       ON ori.CODE = im.ORIGIN
LEFT JOIN CHART_OF_ACCOUNTS coa_s
       ON TRIM(TO_CHAR(coa_s.CODE)) = TRIM(TO_CHAR(im.SALESACCOUNT))
LEFT JOIN CHART_OF_ACCOUNTS coa_p
       ON TRIM(TO_CHAR(coa_p.CODE)) = TRIM(TO_CHAR(im.PURCHASEACCOUNT))
LEFT JOIN CHART_OF_ACCOUNTS coa_i
       ON TRIM(TO_CHAR(coa_i.CODE)) = TRIM(TO_CHAR(im.INVENTORYACCOUNT))
LEFT JOIN CHART_OF_ACCOUNTS coa_c
       ON TRIM(TO_CHAR(coa_c.CODE)) = TRIM(TO_CHAR(im.COGSACCOUNT))
LEFT JOIN ITEMALTERNATEUOMMAP amap
       ON amap.LOCATIONCODE = im.LOCATIONCODE
      AND amap.ITEMCODE = im.ITEMCODE
      AND amap.SLNO = (
            SELECT MIN(x.SLNO)
              FROM ITEMALTERNATEUOMMAP x
             WHERE x.LOCATIONCODE = im.LOCATIONCODE
               AND x.ITEMCODE = im.ITEMCODE
          )
LEFT JOIN UNITOFMEASUREMENT u_alt
       ON u_alt.LOCATIONCODE = amap.LOCATIONCODE
      AND TRIM(UPPER(TO_CHAR(u_alt.UNITCODE))) = TRIM(UPPER(TO_CHAR(amap.ALTERNATEUOMCODE)))
"""


def _normalize_im_cols(im_cols: AbstractSet[str]) -> Set[str]:
    return {str(c).strip().upper() for c in (im_cols or []) if str(c).strip()}


def _im_pick(cols: Set[str], name: str, *, null_sql: str) -> str:
    return f'im.{name}' if name in cols else null_sql


def _im_currentstock_expr(cols: Set[str]) -> str:
    for name in ('CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK', 'QTYONHAND', 'ONHAND', 'TOTALSTOCK'):
        if name in cols:
            return f'NVL(im.{name}, 0) AS CURRENTSTOCK'
    store_cols = sorted([c for c in cols if re.fullmatch('STORE\\d+', c)], key=lambda x: int(x[5:]))
    if store_cols:
        parts = ' + '.join(f'NVL(im.{c}, 0)' for c in store_cols)
        return f'({parts}) AS CURRENTSTOCK'
    return '0 AS CURRENTSTOCK'


def _im_store_expr(cols: Set[str]) -> str:
    if 'STORE' in cols:
        return "NVL(im.STORE, 'STORE1') AS STORE"
    return "'STORE1' AS STORE"


def _im_dept_code_expr(cols: Set[str]) -> str:
    if 'DEPARTMENTCODE' not in cols:
        return 'CAST(NULL AS NUMBER) AS DEPARTMENTCODE'
    return """NVL(
        (SELECT cd0.CODE FROM CATEGORY cd0
         WHERE cd0.CODE = im.DEPARTMENTCODE AND cd0.FLAG = 'D' AND ROWNUM = 1),
        im.DEPARTMENTCODE
    ) AS DEPARTMENTCODE"""


def _im_category_code_expr(cols: Set[str]) -> str:
    if 'CATEGORYCODE' not in cols:
        return 'CAST(NULL AS NUMBER) AS CATEGORYCODE'
    return """NVL(
        (SELECT cc0.CODE FROM CATEGORY cc0
         WHERE cc0.CODE = im.CATEGORYCODE AND cc0.FLAG = 'C' AND ROWNUM = 1),
        im.CATEGORYCODE
    ) AS CATEGORYCODE"""


def build_itemmaster_detail_select_sql(im_cols: AbstractSet[str]) -> str:
    """Build detail SELECT for ITEMMASTER; omits columns missing on this database."""
    cols = _normalize_im_cols(im_cols)
    select_lines = [
        'im.ITEMCODE',
        'im.LOCATIONCODE',
        _im_pick(cols, 'RAWABICODE', null_sql='CAST(NULL AS VARCHAR2(50)) AS RAWABICODE'),
        _im_pick(cols, 'ITEMNAME', null_sql='CAST(NULL AS VARCHAR2(500)) AS ITEMNAME'),
        _im_pick(cols, 'MANUFACTURERID', null_sql='CAST(NULL AS VARCHAR2(50)) AS MANUFACTURERID'),
        _im_pick(cols, 'BRANDCODE', null_sql='CAST(NULL AS NUMBER) AS BRANDCODE'),
        _im_pick(cols, 'SIZECODE', null_sql='CAST(NULL AS NUMBER) AS SIZECODE'),
        _im_pick(cols, 'COLORCODE', null_sql='CAST(NULL AS NUMBER) AS COLORCODE'),
        _im_pick(cols, 'BASEUOM', null_sql="CAST(NULL AS VARCHAR2(20)) AS BASEUOM"),
        _im_pick(cols, 'COSTPRICE', null_sql='CAST(NULL AS NUMBER) AS COSTPRICE'),
        _im_pick(cols, 'RETAILPRICE', null_sql='CAST(NULL AS NUMBER) AS RETAILPRICE'),
        _im_pick(cols, 'WHOLESALEPRICE', null_sql='CAST(NULL AS NUMBER) AS WHOLESALEPRICE'),
        _im_pick(cols, 'THIRDPRICE', null_sql='CAST(NULL AS NUMBER) AS THIRDPRICE'),
        _im_pick(cols, 'BRANCHPRICE', null_sql='CAST(NULL AS NUMBER) AS BRANCHPRICE'),
        _im_pick(cols, 'MAXIMUMLEVEL', null_sql='CAST(NULL AS NUMBER) AS MAXIMUMLEVEL'),
        _im_pick(cols, 'REORDERLEVEL', null_sql='CAST(NULL AS NUMBER) AS REORDERLEVEL'),
        _im_currentstock_expr(cols),
        _im_pick(cols, 'DISCOUNTFLAG', null_sql="CAST(NULL AS VARCHAR2(1)) AS DISCOUNTFLAG"),
        _im_pick(cols, 'COMPANYCODE', null_sql='CAST(NULL AS NUMBER) AS COMPANYCODE'),
        _im_pick(cols, 'SUPCODE', null_sql='CAST(NULL AS NUMBER) AS SUPCODE'),
        _im_pick(cols, 'MAINCATEGORY', null_sql='CAST(NULL AS NUMBER) AS MAINCATEGORY'),
        _im_pick(cols, 'REBATE', null_sql='CAST(NULL AS NUMBER) AS REBATE'),
        _im_pick(cols, 'ITEMNAMEARA', null_sql='CAST(NULL AS VARCHAR2(500)) AS ITEMNAMEARA'),
        _im_pick(cols, 'DESCRIPTION', null_sql='CAST(NULL AS VARCHAR2(500)) AS DESCRIPTION'),
        _im_pick(cols, 'PROPERTY', null_sql='CAST(NULL AS NUMBER) AS PROPERTY'),
        _im_pick(cols, 'ORIGIN', null_sql='CAST(NULL AS NUMBER) AS ORIGIN'),
        _im_pick(cols, 'QUANTITYLIMIT', null_sql='CAST(NULL AS NUMBER) AS QUANTITYLIMIT'),
        _im_pick(cols, 'PACKING', null_sql='CAST(NULL AS VARCHAR2(50)) AS PACKING'),
        _im_pick(cols, 'MINISTRYFACTOR', null_sql='CAST(NULL AS NUMBER) AS MINISTRYFACTOR'),
        _im_pick(cols, 'MINISTRYUNIT', null_sql="CAST(NULL AS VARCHAR2(20)) AS MINISTRYUNIT"),
        _im_pick(cols, 'VATPERCENT', null_sql='CAST(NULL AS NUMBER) AS VATPERCENT'),
        (
            'im.SALESACCOUNT      AS SALES_ACCOUNT'
            if 'SALESACCOUNT' in cols
            else 'CAST(NULL AS VARCHAR2(30)) AS SALES_ACCOUNT'
        ),
        (
            'im.PURCHASEACCOUNT   AS PURCHASE_ACCOUNT'
            if 'PURCHASEACCOUNT' in cols
            else 'CAST(NULL AS VARCHAR2(30)) AS PURCHASE_ACCOUNT'
        ),
        (
            'im.INVENTORYACCOUNT  AS INVENTORY_ACCOUNT'
            if 'INVENTORYACCOUNT' in cols
            else 'CAST(NULL AS VARCHAR2(30)) AS INVENTORY_ACCOUNT'
        ),
        (
            'im.COGSACCOUNT       AS COGS_ACCOUNT'
            if 'COGSACCOUNT' in cols
            else 'CAST(NULL AS VARCHAR2(30)) AS COGS_ACCOUNT'
        ),
        _im_pick(cols, 'ITEMFLAG', null_sql="CAST(NULL AS VARCHAR2(1)) AS ITEMFLAG"),
        _im_store_expr(cols),
        _im_pick(cols, 'DEFAULT_WAREHOUSE_ID', null_sql='CAST(NULL AS NUMBER) AS DEFAULT_WAREHOUSE_ID'),
        (
            "NVL(im.BATCH_TRACKED, 'N') AS BATCH_TRACKED"
            if 'BATCH_TRACKED' in cols
            else "'N' AS BATCH_TRACKED"
        ),
        _im_pick(cols, 'DEFAULT_BIN_STORAGE_ID', null_sql='CAST(NULL AS NUMBER) AS DEFAULT_BIN_STORAGE_ID'),
        _im_pick(cols, 'STAGING_BIN_STORAGE_ID', null_sql='CAST(NULL AS NUMBER) AS STAGING_BIN_STORAGE_ID'),
        _im_dept_code_expr(cols),
        _im_category_code_expr(cols),
        """(CASE WHEN cat_m.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_m.CODE) || ' - ' || NVL(cat_m.NAME, ' ')) END) AS LBL_MAIN_CATEGORY""",
        """(CASE WHEN cat_d.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_d.CODE) || ' - ' || NVL(cat_d.NAME, ' ')) END) AS LBL_DEPARTMENT""",
        """(CASE WHEN cat_c.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_c.CODE) || ' - ' || NVL(cat_c.NAME, ' ')) END) AS LBL_CATEGORY""",
        """(CASE WHEN cat_b.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_b.CODE) || ' - ' || NVL(cat_b.NAME, ' ')) END) AS LBL_BRAND""",
        """(CASE WHEN cat_z.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_z.CODE) || ' - ' || NVL(cat_z.NAME, ' ')) END) AS LBL_SIZE""",
        """(CASE WHEN cat_l.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_l.CODE) || ' - ' || NVL(cat_l.NAME, ' ')) END) AS LBL_COLOR""",
        """(CASE WHEN sup.SUPPLIERCODE IS NOT NULL
          THEN TRIM(TO_CHAR(im.SUPCODE) || ' - ' || NVL(TRIM(sup.SUPPLIERNAME), ' ')) END) AS LBL_SUPPLIER""",
        """(CASE WHEN u_base.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_base.UNITCODE) || ' - ' || NVL(TRIM(u_base.UNITNAME), ' ')) END) AS LBL_BASE_UOM""",
        """(CASE WHEN u_min.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_min.UNITCODE) || ' - ' || NVL(TRIM(u_min.UNITNAME), ' ')) END) AS LBL_MINISTRY_UNIT""",
        """(CASE WHEN prop.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(prop.CODE) || ' - ' || NVL(TRIM(prop.NAME), ' ')) END) AS LBL_PROPERTY""",
        """(CASE WHEN ori.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(ori.CODE) || ' - ' || NVL(TRIM(ori.NAME), ' ')) END) AS LBL_ORIGIN""",
        """(CASE WHEN coa_s.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_s.CODE) || ' - ' || NVL(TRIM(coa_s.NAME), ' ')) END) AS LBL_SALES_ACCOUNT""",
        """(CASE WHEN coa_p.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_p.CODE) || ' - ' || NVL(TRIM(coa_p.NAME), ' ')) END) AS LBL_PURCHASE_ACCOUNT""",
        """(CASE WHEN coa_i.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_i.CODE) || ' - ' || NVL(TRIM(coa_i.NAME), ' ')) END) AS LBL_INVENTORY_ACCOUNT""",
        """(CASE WHEN coa_c.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_c.CODE) || ' - ' || NVL(TRIM(coa_c.NAME), ' ')) END) AS LBL_COGS_ACCOUNT""",
        """(CASE WHEN u_alt.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_alt.UNITCODE) || ' - ' || NVL(TRIM(u_alt.UNITNAME), ' ')) END) AS LBL_ALTERNATE_UOM""",
    ]
    return 'SELECT\n    ' + ',\n    '.join(select_lines) + '\n' + ITEMMASTER_DETAIL_FROM_SQL.strip()


# Legacy static SQL (full column set); prefer build_itemmaster_detail_select_sql at runtime.
ITEMMASTER_DETAIL_SELECT_SQL = build_itemmaster_detail_select_sql(
    {
        'ITEMCODE', 'LOCATIONCODE', 'RAWABICODE', 'ITEMNAME', 'MANUFACTURERID', 'BRANDCODE',
        'SIZECODE', 'COLORCODE', 'BASEUOM', 'COSTPRICE', 'RETAILPRICE', 'WHOLESALEPRICE',
        'THIRDPRICE', 'BRANCHPRICE', 'MAXIMUMLEVEL', 'REORDERLEVEL', 'CURRENTSTOCK',
        'DISCOUNTFLAG', 'COMPANYCODE', 'SUPCODE', 'MAINCATEGORY', 'REBATE',
        'ITEMNAMEARA', 'DESCRIPTION', 'PROPERTY', 'ORIGIN', 'QUANTITYLIMIT', 'PACKING',
        'MINISTRYFACTOR', 'MINISTRYUNIT', 'VATPERCENT', 'SALESACCOUNT', 'PURCHASEACCOUNT',
        'INVENTORYACCOUNT', 'COGSACCOUNT', 'ITEMFLAG', 'STORE', 'DEFAULT_WAREHOUSE_ID',
        'BATCH_TRACKED', 'DEFAULT_BIN_STORAGE_ID', 'STAGING_BIN_STORAGE_ID', 'DEPARTMENTCODE', 'CATEGORYCODE',
    }
)
