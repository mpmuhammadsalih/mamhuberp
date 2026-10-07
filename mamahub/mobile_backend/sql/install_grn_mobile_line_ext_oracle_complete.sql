-- =============================================================================
-- GRN_MOBILE_LINE_EXT — complete install script for Oracle Database
-- =============================================================================
--
-- WHO RUNS THIS
--   ERP schema owner (same Oracle USER each tenant DB uses must have CREATE
--   privileges). Run once per tenant database schema.
--
-- HOW TO RUN (sqlplus: connect string first, script path second)
--   sqlplus schema_user/password@your_tns @d:/path/install_grn_mobile_line_ext_oracle_complete.sql
--   Or SQL Developer: open this file → Run Script (F5).
--
-- IDEMPOTENT: skips CREATE TABLE / CREATE INDEX if objects already exist.
--
-- OPTIONAL — destroy all mobile rows and recreate empty table:
--   DROP TABLE GRN_MOBILE_LINE_EXT CASCADE CONSTRAINTS PURGE;
--
-- Rename legacy column LOCATION_CODE → LOCATIONCODE (if you upgraded from older DDL):
--   ALTER TABLE GRN_MOBILE_LINE_EXT RENAME COLUMN LOCATION_CODE TO LOCATIONCODE;
--
-- =============================================================================

SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  t_cnt PLS_INTEGER;
  i_cnt PLS_INTEGER;
BEGIN
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'GRN_MOBILE_LINE_EXT';

  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating GRN_MOBILE_LINE_EXT...');
    EXECUTE IMMEDIATE
      q'[CREATE TABLE GRN_MOBILE_LINE_EXT (
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
         )]';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('Table GRN_MOBILE_LINE_EXT already exists — skip CREATE TABLE.');
  END IF;

  SELECT COUNT(*) INTO i_cnt FROM user_indexes WHERE index_name = 'IDX_GRN_MOBILE_LINE_EXT_LPO';
  IF i_cnt = 0 THEN
    EXECUTE IMMEDIATE
      q'[CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO ON GRN_MOBILE_LINE_EXT (LPO_NO)]';
    DBMS_OUTPUT.PUT_LINE('Created index IDX_GRN_MOBILE_LINE_EXT_LPO.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('Index IDX_GRN_MOBILE_LINE_EXT_LPO exists — skip.');
  END IF;

  SELECT COUNT(*) INTO i_cnt FROM user_indexes WHERE index_name = 'IDX_GRN_MOBILE_LINE_EXT_LPO_LOC';
  IF i_cnt = 0 THEN
    EXECUTE IMMEDIATE
      q'[CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO_LOC ON GRN_MOBILE_LINE_EXT (LPO_NO, LOCATIONCODE)]';
    DBMS_OUTPUT.PUT_LINE('Created index IDX_GRN_MOBILE_LINE_EXT_LPO_LOC.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('Index IDX_GRN_MOBILE_LINE_EXT_LPO_LOC exists — skip.');
  END IF;
END;
/

-- Comments (rewrites descriptions; harmless to re-run).
COMMENT ON TABLE GRN_MOBILE_LINE_EXT IS
  'Nexa mobile GRN wizard: supplemental line fields keyed by PO + LINE_SEQ + LOCATIONCODE.';
COMMENT ON COLUMN GRN_MOBILE_LINE_EXT.LOCATIONCODE IS
  'Numeric ERP branch/location id (JWT loc or LPO header); 0 = no specific location.';

-- Sanity check
SELECT index_name FROM user_indexes WHERE table_name = 'GRN_MOBILE_LINE_EXT' ORDER BY index_name;

