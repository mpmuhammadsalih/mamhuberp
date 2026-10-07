-- =============================================================================
-- MamaHub - safe installer (create-if-missing only)
-- NEVER drops or deletes existing objects in shared MAMAHUB / Dynamics DB.
-- Prefer: python scripts/apply_schema.py
-- =============================================================================

WHENEVER SQLERROR CONTINUE

PROMPT === Sequences (skip if exist) ===
@@01_sequences/01_create_sequences.sql
@@01_sequences/02_mh_extension_sequences.sql

PROMPT === MH ecommerce extension tables (skip if exist) ===
@@02_tables/06_mh_ecommerce_extensions.sql

PROMPT === MH seed (skip unique conflicts) ===
@@05_seed/01_master_data.sql

PROMPT === Safe install complete (no drops performed) ===
EXIT;
