-- ITEMALTERNATEUOMMAP: variant description + base-row flag (linked to ITEMMASTER).
-- The app also runs ensure_itemalternateuommap_extension_columns() on first save if these are missing.

ALTER TABLE ITEMALTERNATEUOMMAP ADD (
    DESCRIPTION VARCHAR2(500),
    IS_BASE CHAR(1) DEFAULT 'N'
);

COMMENT ON COLUMN ITEMALTERNATEUOMMAP.DESCRIPTION IS 'Variant description; base row typically mirrors ITEMMASTER.DESCRIPTION';
COMMENT ON COLUMN ITEMALTERNATEUOMMAP.IS_BASE IS 'Y = base variant row linked to ITEMMASTER (Base UOM, barcode, prices)';
