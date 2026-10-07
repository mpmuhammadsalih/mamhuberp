-- Item Master: denormalized VIEW for fast read (one SELECT: item row + LBL_* display strings).
--
-- “Create if missing” (Oracle)
--   Oracle has no CREATE VIEW IF NOT EXISTS. Use CREATE OR REPLACE VIEW below:
--   * If the view does not exist → it is created.
--   * If it already exists → it is replaced with this definition.
--   Safe to run on every deploy.
--
-- App integration (runtime)
--   Opening an item in Item Master runs the embedded SELECT in Python (db/itemmaster_detail_select.py);
--   the Oracle view below is optional—for SQL clients, BI, or parity checks with the embedded query.
--
-- Catalog product list (/productlist) reads ``ITEMMASTER`` only (scalar subqueries for names).
--
-- Label columns (LBL_*) must match _itemmaster_detail_view_finalize_row in db/__init__.py and ITEMMASTER_DETAIL_SELECT_SQL in db/itemmaster_detail_select.py.
--
-- If compile fails: remove or rename columns your ITEMMASTER lacks (e.g. BATCH_TRACKED, bin IDs),
-- or fix TBLITEMPROPERTY / TBLITEMORIGIN column names to match your database.

CREATE OR REPLACE VIEW ITEMMASTER_DETAIL_V AS
SELECT
    im.ITEMCODE,
    im.LOCATIONCODE,
    im.RAWABICODE,
    im.ITEMNAME,
    im.MANUFACTURERID,
    im.BRANDCODE,
    im.SIZECODE,
    im.COLORCODE,
    im.BASEUOM,
    im.COSTPRICE,
    im.RETAILPRICE,
    im.WHOLESALEPRICE,
    im.THIRDPRICE,
    im.BRANCHPRICE,
    im.MAXIMUMLEVEL,
    im.REORDERLEVEL,
    im.CURRENTSTOCK,
    im.DISCOUNTFLAG,
    im.COMPANYCODE,
    im.SUPCODE,
    im.MAINCATEGORY,
    im.REBATE,
    im.ITEMNAMEARA,
    im.DESCRIPTION,
    im.PROPERTY,
    im.ORIGIN,
    im.QUANTITYLIMIT,
    im.PACKING,
    im.MINISTRYFACTOR,
    im.MINISTRYUNIT,
    im.VATPERCENT,
    im.SALESACCOUNT      AS SALES_ACCOUNT,
    im.PURCHASEACCOUNT   AS PURCHASE_ACCOUNT,
    im.INVENTORYACCOUNT  AS INVENTORY_ACCOUNT,
    im.COGSACCOUNT       AS COGS_ACCOUNT,
    im.ITEMFLAG,
    NVL(im.STORE, 'STORE1') AS STORE,
    im.DEFAULT_WAREHOUSE_ID,
    NVL(im.BATCH_TRACKED, 'N') AS BATCH_TRACKED,
    im.DEFAULT_BIN_STORAGE_ID,
    im.STAGING_BIN_STORAGE_ID,
    NVL(
        (SELECT cd0.CODE FROM CATEGORY cd0
         WHERE cd0.CODE = im.DEPARTMENTCODE AND cd0.FLAG = 'D' AND ROWNUM = 1),
        im.DEPARTMENTCODE
    ) AS DEPARTMENTCODE,
    NVL(
        (SELECT cc0.CODE FROM CATEGORY cc0
         WHERE cc0.CODE = im.CATEGORYCODE AND cc0.FLAG = 'C' AND ROWNUM = 1),
        im.CATEGORYCODE
    ) AS CATEGORYCODE,
    (CASE WHEN cat_m.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_m.CODE) || ' - ' || NVL(cat_m.NAME, ' ')) END) AS LBL_MAIN_CATEGORY,
    (CASE WHEN cat_d.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_d.CODE) || ' - ' || NVL(cat_d.NAME, ' ')) END) AS LBL_DEPARTMENT,
    (CASE WHEN cat_c.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_c.CODE) || ' - ' || NVL(cat_c.NAME, ' ')) END) AS LBL_CATEGORY,
    (CASE WHEN cat_b.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_b.CODE) || ' - ' || NVL(cat_b.NAME, ' ')) END) AS LBL_BRAND,
    (CASE WHEN cat_z.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_z.CODE) || ' - ' || NVL(cat_z.NAME, ' ')) END) AS LBL_SIZE,
    (CASE WHEN cat_l.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(cat_l.CODE) || ' - ' || NVL(cat_l.NAME, ' ')) END) AS LBL_COLOR,
    (CASE WHEN sup.SUPPLIERCODE IS NOT NULL
          THEN TRIM(TO_CHAR(im.SUPCODE) || ' - ' || NVL(TRIM(sup.SUPPLIERNAME), ' ')) END) AS LBL_SUPPLIER,
    (CASE WHEN u_base.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_base.UNITCODE) || ' - ' || NVL(TRIM(u_base.UNITNAME), ' ')) END) AS LBL_BASE_UOM,
    (CASE WHEN u_min.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_min.UNITCODE) || ' - ' || NVL(TRIM(u_min.UNITNAME), ' ')) END) AS LBL_MINISTRY_UNIT,
    (CASE WHEN prop.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(prop.CODE) || ' - ' || NVL(TRIM(prop.NAME), ' ')) END) AS LBL_PROPERTY,
    (CASE WHEN ori.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(ori.CODE) || ' - ' || NVL(TRIM(ori.NAME), ' ')) END) AS LBL_ORIGIN,
    (CASE WHEN coa_s.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_s.CODE) || ' - ' || NVL(TRIM(coa_s.NAME), ' ')) END) AS LBL_SALES_ACCOUNT,
    (CASE WHEN coa_p.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_p.CODE) || ' - ' || NVL(TRIM(coa_p.NAME), ' ')) END) AS LBL_PURCHASE_ACCOUNT,
    (CASE WHEN coa_i.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_i.CODE) || ' - ' || NVL(TRIM(coa_i.NAME), ' ')) END) AS LBL_INVENTORY_ACCOUNT,
    (CASE WHEN coa_c.CODE IS NOT NULL
          THEN TRIM(TO_CHAR(coa_c.CODE) || ' - ' || NVL(TRIM(coa_c.NAME), ' ')) END) AS LBL_COGS_ACCOUNT,
    (CASE WHEN u_alt.UNITCODE IS NOT NULL
          THEN TRIM(TO_CHAR(u_alt.UNITCODE) || ' - ' || NVL(TRIM(u_alt.UNITNAME), ' ')) END) AS LBL_ALTERNATE_UOM
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
      AND TRIM(UPPER(TO_CHAR(u_alt.UNITCODE))) = TRIM(UPPER(TO_CHAR(amap.ALTERNATEUOMCODE)));
