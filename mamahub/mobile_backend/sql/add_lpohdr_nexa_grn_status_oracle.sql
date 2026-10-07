-- LPOHDR: mobile/completed GRN status (updated by Nexa API on successful goods-receipt POST).
-- Default Pending; set to Completed when GRN is submitted via the mobile wizard.
--
-- Replace LPOHDR with your ERP header synonym if applicable.
--
-- ALTER TABLE LPOHDR ADD ( NEXA_GRN_STATUS VARCHAR2(40) DEFAULT 'Pending' NOT NULL );

DECLARE
  v_cnt NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM user_tab_columns
   WHERE table_name = 'LPOHDR' AND column_name = 'NEXA_GRN_STATUS';
  IF v_cnt = 0 THEN
    EXECUTE IMMEDIATE
      q'[ALTER TABLE LPOHDR ADD ( NEXA_GRN_STATUS VARCHAR2(40) DEFAULT 'Pending' NOT NULL )]';
    DBMS_OUTPUT.PUT_LINE('Added LPOHDR.NEXA_GRN_STATUS');
  ELSE
    DBMS_OUTPUT.PUT_LINE('LPOHDR.NEXA_GRN_STATUS already exists — skip.');
  END IF;
END;
/
