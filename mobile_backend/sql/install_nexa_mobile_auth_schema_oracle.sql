-- =============================================================================
-- Nexa Mobile API — AUTH / TENANT CATALOG TABLES (Oracle)
-- =============================================================================
--
-- AFFECTED SCHEMA: the Oracle USER in .env → ORACLE_USER / ORACLE_DSN
--   This is NOT your tenant ERP inventory schema unless you purposely use one
--   database user for everything.
--
-- TABLES CREATED (if missing — script is idempotent):
--   TENANT_DATABASES   — ERP DB connections per TENANT_ID (JWT carries tenant_id)
--   LOGIN_USERS       — Users, password_hash (Werkzeug), role_id, default tenant
--   ROLE_PERMISSIONS  — Permission keys per role (MENU_PATH matches API gates)
--
-- WHAT YOU DO AFTER THIS SCRIPT:
--   1) INSERT into TENANT_DATABASES (tenant_id + IP/port/service/username/password)
--   2) INSERT into LOGIN_USERS (username + werkzeug PASSWORD_HASH + role_id + tenant_id)
--   3) INSERT into ROLE_PERMISSIONS for each ROLE_ID referenced by LOGIN_USERS
--   4) Ensure tenant schemas have ERP tables (ITEMMASTER, etc.). This script does NOT
--      create ERP core tables.
--
-- PASSWORD HASH (run where werkzeug is installed, e.g. erp_api venv):
--   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YOUR_PASSWORD'))"
--
-- HOW TO RUN:
--   sqlplus ORACLE_USER/password@YOUR_TSN @install_nexa_mobile_auth_schema_oracle.sql
--   Or SQL Developer: open file → Run Script (F5)
--
-- =============================================================================

SET SERVEROUTPUT ON SIZE UNLIMITED

--------------------------------------------------------------------------------
-- TENANT_DATABASES (erp_api/database/oracle_pool.py)
--------------------------------------------------------------------------------
DECLARE
  t_cnt PLS_INTEGER;
BEGIN
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'TENANT_DATABASES';

  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating TENANT_DATABASES...');
    EXECUTE IMMEDIATE
      q'[CREATE TABLE TENANT_DATABASES (
           TENANT_ID      VARCHAR2(64 CHAR)  NOT NULL,
           DISPLAY_NAME   VARCHAR2(200 CHAR),
           ACTIVE_FLAG    CHAR(1 CHAR) DEFAULT 'Y',
           IP             VARCHAR2(200 CHAR),
           PORT           NUMBER(10) DEFAULT 1521,
           SERVICE_NAME   VARCHAR2(128 CHAR),
           USERNAME       VARCHAR2(128 CHAR),
           PASSWORD       VARCHAR2(256 CHAR),
           CONSTRAINT PK_TENANT_DATABASES PRIMARY KEY (TENANT_ID)
         )]';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('TENANT_DATABASES exists — skipped CREATE.');
  END IF;
END;
/

COMMENT ON TABLE TENANT_DATABASES IS 'Nexa mobile: ERP DB connections per tenant; JWT tenant_id selects a row.';
COMMENT ON COLUMN TENANT_DATABASES.IP IS 'Hostname or scan for tenant listener.';
COMMENT ON COLUMN TENANT_DATABASES.SERVICE_NAME IS 'SERVICE_NAME / PDB service for ERP schema.';
COMMENT ON COLUMN TENANT_DATABASES.USERNAME IS 'Oracle ERP user the API connects as for this tenant.';
COMMENT ON COLUMN TENANT_DATABASES.PASSWORD IS 'Oracle password for that ERP user (plain text for driver).';


--------------------------------------------------------------------------------
-- LOGIN_USERS (erp_api/services/auth_service.py + tenant_service.py)
--------------------------------------------------------------------------------
DECLARE
  t_cnt PLS_INTEGER;
  i_cnt PLS_INTEGER;
BEGIN
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'LOGIN_USERS';

  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating LOGIN_USERS...');
    EXECUTE IMMEDIATE
      q'[CREATE TABLE LOGIN_USERS (
           USERNAME              VARCHAR2(128 CHAR)  NOT NULL,
           PASSWORD_HASH         VARCHAR2(512 CHAR)  NOT NULL,
           ROLE_ID               VARCHAR2(64 CHAR),
           EMPLOYEECODE          VARCHAR2(128 CHAR),
           TENANT_ID             VARCHAR2(64 CHAR),
           ACTIVE_FLAG           CHAR(1 CHAR) DEFAULT 'Y',
           MULTILOCATIONS_VIEW   CHAR(1 CHAR) DEFAULT 'N',
           ALLOWED_TENANT_IDS    CLOB,
           CONSTRAINT PK_LOGIN_USERS PRIMARY KEY (USERNAME)
         )]';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('LOGIN_USERS exists — skipped CREATE.');
  END IF;

  SELECT COUNT(*) INTO i_cnt FROM user_indexes WHERE index_name = 'IDX_LOGIN_USERS_EMP_UPPER';
  IF i_cnt = 0 THEN
    EXECUTE IMMEDIATE
      q'[CREATE INDEX IDX_LOGIN_USERS_EMP_UPPER ON LOGIN_USERS (UPPER(TRIM(EMPLOYEECODE)))]';
    DBMS_OUTPUT.PUT_LINE('Created IDX_LOGIN_USERS_EMP_UPPER.');
  END IF;
END;
/

COMMENT ON TABLE LOGIN_USERS IS 'Mobile login: PASSWORD_HASH = Werkzeug pbkdf2; match username or EMPLOYEECODE.';
COMMENT ON COLUMN LOGIN_USERS.MULTILOCATIONS_VIEW IS 'Y allows tenant picker; filter with ALLOWED_TENANT_IDS JSON or CSV.';


--------------------------------------------------------------------------------
-- ROLE_PERMISSIONS (erp_api/services/auth_service.py get_role_permissions)
--------------------------------------------------------------------------------
DECLARE
  t_cnt PLS_INTEGER;
  i_cnt PLS_INTEGER;
BEGIN
  SELECT COUNT(*) INTO t_cnt FROM user_tables WHERE table_name = 'ROLE_PERMISSIONS';

  IF t_cnt = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Creating ROLE_PERMISSIONS...');
    EXECUTE IMMEDIATE
      q'[CREATE TABLE ROLE_PERMISSIONS (
           ROLE_ID     VARCHAR2(64 CHAR)  NOT NULL,
           MENU_PATH   VARCHAR2(256 CHAR) NOT NULL,
           CONSTRAINT PK_ROLE_PERMISSIONS PRIMARY KEY (ROLE_ID, MENU_PATH)
         )]';
    DBMS_OUTPUT.PUT_LINE('  Done.');
  ELSE
    DBMS_OUTPUT.PUT_LINE('ROLE_PERMISSIONS exists — skipped CREATE.');
  END IF;

  SELECT COUNT(*) INTO i_cnt FROM user_indexes WHERE index_name = 'IDX_ROLE_PERMISSIONS_ROLE';
  IF i_cnt = 0 THEN
    EXECUTE IMMEDIATE
      q'[CREATE INDEX IDX_ROLE_PERMISSIONS_ROLE ON ROLE_PERMISSIONS (ROLE_ID)]';
    DBMS_OUTPUT.PUT_LINE('Created IDX_ROLE_PERMISSIONS_ROLE.');
  END IF;
END;
/

COMMENT ON TABLE ROLE_PERMISSIONS IS 'MENU_PATH values must match FastAPI require_permission(...) keys.';


--------------------------------------------------------------------------------
-- EXAMPLE DATA (COMMENTED — edit placeholders, uncomment to run once)
--------------------------------------------------------------------------------
/*
-- Tenant row: points mobile API at one ERP Oracle schema when JWT tenant_id = DEMO
INSERT INTO TENANT_DATABASES
  (TENANT_ID, DISPLAY_NAME, ACTIVE_FLAG, IP, PORT, SERVICE_NAME, USERNAME, PASSWORD)
VALUES
  ('DEMO', 'Demo company', 'Y', '192.168.1.10', 1521, 'ORCLPDB1', 'ERP_SCHEMA_USER', 'ERP_SCHEMA_PASSWORD');

-- User: replace PASSWORD_HASH with output of generate_password_hash('Secret123!')
INSERT INTO LOGIN_USERS
  (USERNAME, PASSWORD_HASH, ROLE_ID, EMPLOYEECODE, TENANT_ID, ACTIVE_FLAG, MULTILOCATIONS_VIEW, ALLOWED_TENANT_IDS)
VALUES
  ('demo.user',
   'paste_werkzeug_hash_here',
   'MOBILE_STOCK',
   'EMP001',
   'DEMO',
   'Y',
   'N',
   NULL);

-- Permissions bound to ROLE_ID (minimum set used by routes in this codebase)
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'dashboard.dashboard');
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'itemmaster.productlist');
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'purchase.purchase_order_list');
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'purchase.purchase_order_add');
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'sales.sales_invoice');
INSERT INTO ROLE_PERMISSIONS (ROLE_ID, MENU_PATH) VALUES ('MOBILE_STOCK', 'accounts.customer_ledger_page');

COMMIT;
*/


PROMPT install_nexa_mobile_auth_schema_oracle.sql finished — see NEXA_MOBILE_SCHEMA.md for next steps.
