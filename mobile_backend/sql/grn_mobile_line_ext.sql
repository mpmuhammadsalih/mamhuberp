-- Optional side table for mobile Goods Receiving line captures when LPODTL
-- does not expose BONUS/BATCH/BIN/etc., or when you prefer not to mutate legacy columns.
-- Run once per tenant Oracle schema used by Nexa ERP API.

CREATE TABLE GRN_MOBILE_LINE_EXT (
  LPO_NO            VARCHAR2(64 CHAR)  NOT NULL,
  LOCATIONCODE      NUMBER(18)         DEFAULT 0 NOT NULL,
  LINE_SEQ          NUMBER(10)         NOT NULL,
  ITEM_CODE         VARCHAR2(128 CHAR) NOT NULL,
  RECEIVED_QTY      NUMBER(18, 4),
  BONUS_QTY         NUMBER(18, 4),
  FOC_FLAG          CHAR(1 CHAR),
  BONUS_BASE_UNIT   NUMBER(18, 4),
  BATCH_NO          VARCHAR2(128 CHAR),
  EXPIRY_DATE       DATE,
  STORE_CODE        VARCHAR2(64 CHAR),
  BIN_CODE          VARCHAR2(64 CHAR),
  UPDATED_BY        VARCHAR2(128 CHAR),
  UPDATED_AT        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT PK_GRN_MOBILE_LINE_EXT PRIMARY KEY (LPO_NO, LINE_SEQ, LOCATIONCODE)
);

CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO ON GRN_MOBILE_LINE_EXT (LPO_NO);
CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO_LOC ON GRN_MOBILE_LINE_EXT (LPO_NO, LOCATIONCODE);

COMMENT ON TABLE GRN_MOBILE_LINE_EXT IS
  'Nexa mobile GRN wizard: supplemental line fields keyed by PO + LINE_SEQ + LOCATIONCODE.';
COMMENT ON COLUMN GRN_MOBILE_LINE_EXT.LOCATIONCODE IS
  'Numeric ERP branch/location id (JWT loc or LPO header); 0 = no specific location.';

-- ── Upgrade from older column name LOCATION_CODE (NUMBER or VARCHAR2) ────────
-- ALTER TABLE GRN_MOBILE_LINE_EXT RENAME COLUMN LOCATION_CODE TO LOCATIONCODE;
-- Rebuild PK / index names if Oracle requires after rename.
