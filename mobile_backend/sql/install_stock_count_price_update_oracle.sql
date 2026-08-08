-- =============================================================================
-- STOCK_COUNT_PRICE_HDR + STOCK_COUNT_PRICE_UPDATE + STOCK_COUNT_DTL retail columns
-- =============================================================================
-- Run once per tenant ERP schema (same user as mobile stock count).
-- Idempotent: skips objects/columns that already exist.
-- =============================================================================

SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  t_cnt PLS_INTEGER;
  c_cnt PLS_INTEGER;
BEGIN
  -- Price update session header (one row per stock count LOCATIONCODE + COUNT_NO)
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'STOCK_COUNT_PRICE_HDR';
  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating STOCK_COUNT_PRICE_HDR...');
    EXECUTE IMMEDIATE q'[
      CREATE TABLE STOCK_COUNT_PRICE_HDR (
        LOCATIONCODE      NUMBER(18)       NOT NULL,
        COUNT_NO          NUMBER(18)       NOT NULL,
        COUNT_DATE        DATE             DEFAULT TRUNC(SYSDATE),
        WAREHOUSE_ID      NUMBER(18),
        STATUS            VARCHAR2(20 CHAR) DEFAULT 'PENDING' NOT NULL,
        REMARKS           VARCHAR2(500 CHAR),
        CREATED_BY        VARCHAR2(50 CHAR),
        CREATED_AT        TIMESTAMP(6)     DEFAULT SYSTIMESTAMP NOT NULL,
        POSTED_BY         VARCHAR2(50 CHAR),
        POSTED_AT         TIMESTAMP(6),
        PDT_DEVICE_ID     VARCHAR2(50 CHAR),
        BATCH_NO          NUMBER(18),
        CONSTRAINT PK_STOCK_COUNT_PRICE_HDR PRIMARY KEY (LOCATIONCODE, COUNT_NO)
      )]';
    EXECUTE IMMEDIATE
      'CREATE INDEX IDX_SC_PRICE_HDR_STATUS ON STOCK_COUNT_PRICE_HDR (STATUS, LOCATIONCODE, COUNT_NO)';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('STOCK_COUNT_PRICE_HDR already exists — skip.');
  END IF;

  -- Detail: retail price lines per item on that count
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'STOCK_COUNT_PRICE_UPDATE';
  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating STOCK_COUNT_PRICE_UPDATE...');
    EXECUTE IMMEDIATE q'[
      CREATE TABLE STOCK_COUNT_PRICE_UPDATE (
        LOCATIONCODE      NUMBER(18)       NOT NULL,
        COUNT_NO          NUMBER(18)       NOT NULL,
        ITEMCODE          NUMBER(18)       NOT NULL,
        LINE_NO           NUMBER(10),
        OLD_RETAIL_PRICE  NUMBER(18, 4),
        NEW_RETAIL_PRICE  NUMBER(18, 4)    NOT NULL,
        STATUS            VARCHAR2(20 CHAR) DEFAULT 'PENDING' NOT NULL,
        UPDATED_BY        VARCHAR2(50 CHAR),
        UPDATED_AT        TIMESTAMP(6)     DEFAULT SYSTIMESTAMP NOT NULL,
        BATCH_NO          NUMBER(18),
        CONSTRAINT PK_STOCK_COUNT_PRICE_UPD PRIMARY KEY (LOCATIONCODE, COUNT_NO, ITEMCODE)
      )]';
    EXECUTE IMMEDIATE
      'CREATE INDEX IDX_SC_PRICE_UPD_STATUS ON STOCK_COUNT_PRICE_UPDATE (STATUS, LOCATIONCODE, COUNT_NO)';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('STOCK_COUNT_PRICE_UPDATE already exists — skip.');
  END IF;

  -- Sequence for new price-update batches (links HDR <-> UPDATE via BATCH_NO)
  SELECT COUNT(*) INTO t_cnt FROM user_sequences WHERE sequence_name = 'SEQ_STOCK_COUNT_PRICE_BATCH';
  IF t_cnt = 0 THEN
    EXECUTE IMMEDIATE
      'CREATE SEQUENCE SEQ_STOCK_COUNT_PRICE_BATCH START WITH 1 INCREMENT BY 1 NOCACHE';
    DBMS_OUTPUT.PUT_LINE('Created SEQ_STOCK_COUNT_PRICE_BATCH.');
  END IF;

  SELECT COUNT(*) INTO c_cnt
    FROM user_tab_columns
   WHERE table_name = 'STOCK_COUNT_PRICE_HDR' AND column_name = 'BATCH_NO';
  IF c_cnt = 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE STOCK_COUNT_PRICE_HDR ADD (BATCH_NO NUMBER(18))';
    EXECUTE IMMEDIATE q'[
      UPDATE STOCK_COUNT_PRICE_HDR
         SET BATCH_NO = LOCATIONCODE * 1000000 + COUNT_NO
       WHERE BATCH_NO IS NULL]';
    DBMS_OUTPUT.PUT_LINE('Added STOCK_COUNT_PRICE_HDR.BATCH_NO');
  END IF;

  SELECT COUNT(*) INTO c_cnt
    FROM user_tab_columns
   WHERE table_name = 'STOCK_COUNT_PRICE_UPDATE' AND column_name = 'BATCH_NO';
  IF c_cnt = 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE STOCK_COUNT_PRICE_UPDATE ADD (BATCH_NO NUMBER(18))';
    EXECUTE IMMEDIATE q'[
      UPDATE STOCK_COUNT_PRICE_UPDATE u
         SET BATCH_NO = (
               SELECT h.BATCH_NO
                 FROM STOCK_COUNT_PRICE_HDR h
                WHERE h.LOCATIONCODE = u.LOCATIONCODE
                  AND h.COUNT_NO = u.COUNT_NO
             )
       WHERE BATCH_NO IS NULL]';
    DBMS_OUTPUT.PUT_LINE('Added STOCK_COUNT_PRICE_UPDATE.BATCH_NO');
  END IF;

  BEGIN
    EXECUTE IMMEDIATE
      'CREATE INDEX IDX_SC_PRICE_UPD_BATCH ON STOCK_COUNT_PRICE_UPDATE (BATCH_NO)';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLCODE != -955 THEN RAISE; END IF;
  END;
  BEGIN
    EXECUTE IMMEDIATE
      'CREATE UNIQUE INDEX UK_SC_PRICE_HDR_BATCH ON STOCK_COUNT_PRICE_HDR (BATCH_NO)';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLCODE != -955 THEN RAISE; END IF;
  END;

  -- Optional columns on count detail (shown in mobile + applied on POST)
  FOR c_rec IN (
    SELECT 'OLD_RETAIL_PRICE' AS col_name FROM dual
    UNION ALL SELECT 'NEW_RETAIL_PRICE' FROM dual
  ) LOOP
    SELECT COUNT(*) INTO c_cnt
      FROM user_tab_columns
     WHERE table_name = 'STOCK_COUNT_DTL'
       AND column_name = c_rec.col_name;
    IF c_cnt = 0 THEN
      EXECUTE IMMEDIATE
        'ALTER TABLE STOCK_COUNT_DTL ADD (' || c_rec.col_name || ' NUMBER(18, 4))';
      DBMS_OUTPUT.PUT_LINE('Added STOCK_COUNT_DTL.' || c_rec.col_name);
    END IF;
  END LOOP;
END;
/

COMMENT ON TABLE STOCK_COUNT_PRICE_HDR IS
  'Nexa mobile: retail price update session header (linked to STOCK_COUNT_HDR by LOCATIONCODE + COUNT_NO).';
COMMENT ON TABLE STOCK_COUNT_PRICE_UPDATE IS
  'Nexa mobile: retail price lines for a count (applied to ITEMMASTER when count is POSTED).';
