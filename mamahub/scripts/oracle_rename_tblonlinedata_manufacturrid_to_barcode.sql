-- TBLONLINEDATA: rename legacy column to BARCODE
-- Run in SQL*Plus / SQL Developer as the schema user that owns TBLONLINEDATA (often the HO tenant user).
-- After this, refresh Tasveek; the app reads column names from the data dictionary.
-- If you have views or PL/SQL referencing MANUFACTURRID, recompile or update them.

-- Default: unquoted identifier becomes MANUFACTURRID in Oracle
ALTER TABLE TBLONLINEDATA RENAME COLUMN MANUFACTURRID TO BARCODE;

-- If your old name was different, use one of these instead (comment out the line above first):
-- ALTER TABLE TBLONLINEDATA RENAME COLUMN MANUFACTURERID TO BARCODE;
-- ALTER TABLE TBLONLINEDATA RENAME COLUMN "manufacturrid" TO BARCODE;
