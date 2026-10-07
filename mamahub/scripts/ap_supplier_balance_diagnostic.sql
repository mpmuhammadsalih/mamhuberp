-- AP Supplier Balance Diagnostic (Oracle)
-- Purpose:
-- 1) Find suppliers that are falling back to control-account TB balance
-- 2) Show shared PAYABLEACCOUNT mappings
-- 3) Spot missing PARTY_TYPE/PARTY_CODE supplier tagging
--
-- Run in SQL*Plus / SQL Developer.

SET PAGESIZE 200
SET LINESIZE 220
SET TRIMSPOOL ON

PROMPT
PROMPT === 0) Supplier master overview (payable account mapping) ===
SELECT
  s.locationcode,
  s.suppliercode,
  s.suppliername,
  s.payableaccount
FROM supplier s
ORDER BY s.payableaccount, s.suppliercode;

PROMPT
PROMPT === 1) PAYABLEACCOUNT shared by multiple suppliers ===
SELECT
  s.payableaccount,
  COUNT(*) AS supplier_count
FROM supplier s
GROUP BY s.payableaccount
HAVING COUNT(*) > 1
ORDER BY supplier_count DESC, s.payableaccount;

PROMPT
PROMPT === 2) Supplier party-tagged GL balances by account (credit - debit) ===
SELECT
  d.party_code AS suppliercode,
  d.account_code,
  ROUND(SUM(NVL(d.credit, 0) - NVL(d.debit, 0)), 2) AS supplier_acc_balance
FROM gl_dtl d
WHERE UPPER(NVL(d.party_type, '')) = 'SUPPLIER'
  AND d.party_code IS NOT NULL
GROUP BY d.party_code, d.account_code
ORDER BY d.party_code, d.account_code;

PROMPT
PROMPT === 3) Suppliers with NO supplier-tagged GL rows (likely fallback users) ===
SELECT
  s.locationcode,
  s.suppliercode,
  s.suppliername,
  s.payableaccount
FROM supplier s
WHERE NOT EXISTS (
  SELECT 1
  FROM gl_dtl d
  WHERE UPPER(NVL(d.party_type, '')) = 'SUPPLIER'
    AND TRIM(TO_CHAR(d.party_code)) = TRIM(TO_CHAR(s.suppliercode))
)
ORDER BY s.payableaccount, s.suppliercode;

PROMPT
PROMPT === 4) Suppliers whose supplier-tagged rows exist, but NOT on mapped PAYABLEACCOUNT ===
SELECT
  s.locationcode,
  s.suppliercode,
  s.suppliername,
  s.payableaccount,
  COUNT(*) AS tagged_rows_other_accounts
FROM supplier s
JOIN gl_dtl d
  ON UPPER(NVL(d.party_type, '')) = 'SUPPLIER'
 AND TRIM(TO_CHAR(d.party_code)) = TRIM(TO_CHAR(s.suppliercode))
 AND TRIM(TO_CHAR(d.account_code)) <> TRIM(TO_CHAR(s.payableaccount))
GROUP BY
  s.locationcode,
  s.suppliercode,
  s.suppliername,
  s.payableaccount
ORDER BY tagged_rows_other_accounts DESC, s.suppliercode;

PROMPT
PROMPT === 5) Control account TB balances (credit - debit) for supplier payable accounts ===
SELECT
  s.payableaccount AS account_code,
  ROUND(SUM(NVL(d.credit, 0) - NVL(d.debit, 0)), 2) AS control_balance
FROM supplier s
LEFT JOIN gl_dtl d
  ON TRIM(TO_CHAR(d.account_code)) = TRIM(TO_CHAR(s.payableaccount))
GROUP BY s.payableaccount
ORDER BY s.payableaccount;

PROMPT
PROMPT === 6) Side-by-side: supplier tagged balance vs mapped control-account balance ===
WITH supplier_party AS (
  SELECT
    TRIM(TO_CHAR(d.party_code)) AS suppliercode,
    ROUND(SUM(NVL(d.credit, 0) - NVL(d.debit, 0)), 2) AS supplier_party_balance
  FROM gl_dtl d
  WHERE UPPER(NVL(d.party_type, '')) = 'SUPPLIER'
    AND d.party_code IS NOT NULL
  GROUP BY TRIM(TO_CHAR(d.party_code))
),
control_acc AS (
  SELECT
    TRIM(TO_CHAR(d.account_code)) AS account_code,
    ROUND(SUM(NVL(d.credit, 0) - NVL(d.debit, 0)), 2) AS control_balance
  FROM gl_dtl d
  GROUP BY TRIM(TO_CHAR(d.account_code))
)
SELECT
  s.locationcode,
  s.suppliercode,
  s.suppliername,
  s.payableaccount,
  NVL(sp.supplier_party_balance, 0) AS supplier_party_balance,
  NVL(ca.control_balance, 0) AS mapped_control_balance,
  CASE
    WHEN sp.supplier_party_balance IS NULL THEN 'FALLBACK (NO PARTY TAG)'
    ELSE 'PARTY-TAGGED'
  END AS balance_source_hint
FROM supplier s
LEFT JOIN supplier_party sp
  ON sp.suppliercode = TRIM(TO_CHAR(s.suppliercode))
LEFT JOIN control_acc ca
  ON ca.account_code = TRIM(TO_CHAR(s.payableaccount))
ORDER BY s.payableaccount, s.suppliercode;

