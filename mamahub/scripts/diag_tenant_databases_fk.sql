-- Run in the SAME Oracle schema (user) as TENANT_DATABASES — usually your auth / login DB.
-- Replace OWNER if needed, e.g. AND ac.OWNER = 'TEST_HAYYA'

-- 1) Foreign keys FROM tenant_databases → parent table (ORA-02291 = value missing in parent)
SELECT ac.constraint_name AS fk_name,
       acc.column_name    AS tenant_databases_column,
       pc.table_name      AS parent_table,
       pcc.column_name    AS parent_column
FROM   all_constraints ac
JOIN   all_cons_columns acc ON ac.owner = acc.owner AND ac.constraint_name = acc.constraint_name
JOIN   all_constraints pc ON ac.r_owner = pc.owner AND ac.r_constraint_name = pc.constraint_name
JOIN   all_cons_columns pcc ON pc.owner = pcc.owner AND pc.constraint_name = pcc.constraint_name
                             AND acc.position = pcc.position
WHERE  ac.constraint_type = 'R'
AND    ac.table_name = 'TENANT_DATABASES'
ORDER BY ac.constraint_name, acc.position;

-- 2) Optional: describe the failing constraint by name (from error text)
-- SELECT * FROM all_constraints WHERE constraint_name = 'FK_TENANT_DATAB_LOGIN__0';

-- After you see parent_table / parent_column:
-- - Insert or update a row in PARENT so (parent_column) equals the value you put in TENANT_DATABASES.(tenant_databases_column).
-- - Or set the child column to NULL (if Oracle allows NULL for that FK column).
-- - Or drop/change the FK if it was created by mistake (DBA only).
