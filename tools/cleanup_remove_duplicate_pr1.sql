-- =====================================================================
-- Cleanup: remove the DUPLICATE posted Purchase Return document #1
-- (voucher PR-1-1) that was created by the old double-post bug.
--
-- Context (from the screenshots):
--   * RETURNHDR has TWO docs #1 and #2, BOTH = GOLDEN BABY TRADING 24.00
--     -> these are duplicates of the SAME return (order/request #1).
--   * The "real" document to KEEP is #2 (request #1 is linked to it via
--     TEMPRETURNHDR.TRANSACTIONNO = 2).
--   * Document #1 is the ORPHAN duplicate -> remove it AND reverse the
--     stock it deducted, then delete its ITEMJOURNAL rows.
--
-- Assumptions (CHANGE if different): LOCATIONCODE = 1, RESETNO = 1,
--   document to remove GOODSRETURNNO = 1.
--
-- HOW TO USE:
--   1. Run SECTION A (read-only) first and EYEBALL the results.
--      - Confirm RETURNHDR #1 is the GOLDEN BABY 24.00 duplicate.
--      - Check whether any line is batch-tracked / uses WAREHOUSE_ID /
--        STORAGE_ID (rows in WAREHOUSE_STOCK / BIN_STOCK / item lots).
--        If YES, do NOT run SECTION B as-is -- ping me with the output
--        and I will extend the reversal for batch/warehouse/bin.
--   2. If lines are simple (base UOM, no batch, no warehouse_id), run
--      SECTION B inside a transaction, verify with SECTION A again,
--      then COMMIT (or ROLLBACK if anything looks wrong).
-- =====================================================================

-- ============================ SECTION A ==============================
-- READ-ONLY verification. Run these and review BEFORE any change.

-- A1. The two posted documents (should both be GOLDEN BABY 24.00):
SELECT GOODSRETURNNO, LOCATIONCODE, RETURNDATE, SUPPLIERCODE,
       RETURNAMOUNT, RETURNTYPE, DELFLAG, RESETNO
FROM   RETURNHDR
WHERE  LOCATIONCODE = 1 AND RESETNO = 1
AND    GOODSRETURNNO IN (1, 2)
ORDER  BY GOODSRETURNNO;

-- A2. Lines of the document being removed (#1):
SELECT GOODSRETURNNO, ITEMCODE, UOM, QUANTITY, RATE, DISCOUNT,
       CONVERSIONFACTOR, STORE, WAREHOUSE_ID, STORAGE_ID, LOT_ID
FROM   RETURNDTL
WHERE  LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1
ORDER  BY ITEMCODE;

-- A3. Journal rows written by this return post (#1):
SELECT RECEIPTNO, LINENO, ITEMCODE, UOM, QTY, RATE, AMOUNT,
       TRANSTYPE, SOURCE_DOC, SOURCE_NO, WAREHOUSE_ID
FROM   ITEMJOURNAL
WHERE  LOCATIONCODE = 1 AND RESETNO = 1
AND    RECEIPTNO = 1
AND    TRANSTYPE = 'PURCHASE_RETURN'
ORDER  BY LINENO;

-- A4. Current stock of the affected items (for sanity before/after):
SELECT im.ITEMCODE, im.ITEMNAME, im.CURRENTSTOCK
FROM   ITEMMASTER im
WHERE  im.LOCATIONCODE = 1
AND    im.ITEMCODE IN (SELECT ITEMCODE FROM RETURNDTL
                       WHERE LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1)
ORDER  BY im.ITEMCODE;

-- A5. Does this return use batch lots / warehouse / bin?  If any row
--     returns > 0 you MUST handle those reversals too (ask me):
SELECT 'returndtl_with_lot'    AS what, COUNT(*) AS cnt FROM RETURNDTL
  WHERE LOCATIONCODE=1 AND RESETNO=1 AND GOODSRETURNNO=1 AND LOT_ID IS NOT NULL
UNION ALL
SELECT 'returndtl_with_wh',     COUNT(*) FROM RETURNDTL
  WHERE LOCATIONCODE=1 AND RESETNO=1 AND GOODSRETURNNO=1 AND WAREHOUSE_ID IS NOT NULL
UNION ALL
SELECT 'returndtl_with_bin',    COUNT(*) FROM RETURNDTL
  WHERE LOCATIONCODE=1 AND RESETNO=1 AND GOODSRETURNNO=1 AND STORAGE_ID IS NOT NULL;


-- ============================ SECTION B ==============================
-- DESTRUCTIVE cleanup for the SIMPLE case (base UOM, no batch / no
-- warehouse_id / no storage_id). Run as ONE transaction; verify; COMMIT.
-- If SECTION A5 showed lot/warehouse/bin usage, STOP and ask for the
-- extended version.

-- B1. Reverse ITEMMASTER stock that this duplicate post DEDUCTED
--     (a return deducts stock, so removing it ADDS the qty back).
UPDATE ITEMMASTER im
SET    im.CURRENTSTOCK = NVL(im.CURRENTSTOCK, 0) + (
         SELECT NVL(SUM(NVL(d.QUANTITY,0) * NVL(d.CONVERSIONFACTOR,1)), 0)
         FROM   RETURNDTL d
         WHERE  d.LOCATIONCODE = 1 AND d.RESETNO = 1 AND d.GOODSRETURNNO = 1
         AND    d.ITEMCODE = im.ITEMCODE
       )
WHERE  im.LOCATIONCODE = 1
AND    im.ITEMCODE IN (SELECT ITEMCODE FROM RETURNDTL
                       WHERE LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1);

-- B2. Keep the base-UOM row of ITEMALTERNATEUOMMAP in sync with ITEMMASTER.
UPDATE ITEMALTERNATEUOMMAP a
SET    a.CURRENTSTOCK = (
         SELECT im.CURRENTSTOCK FROM ITEMMASTER im
         WHERE  im.LOCATIONCODE = a.LOCATIONCODE AND im.ITEMCODE = a.ITEMCODE
       )
WHERE  a.LOCATIONCODE = 1
AND    NVL(a.IS_BASE, 'N') = 'Y'
AND    a.ITEMCODE IN (SELECT ITEMCODE FROM RETURNDTL
                      WHERE LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1);

-- B2b. Add qty back to the specific (non-base) UOM rows that were sold/returned.
UPDATE ITEMALTERNATEUOMMAP a
SET    a.CURRENTSTOCK = NVL(a.CURRENTSTOCK, 0) + (
         SELECT NVL(SUM(NVL(d.QUANTITY,0)), 0)
         FROM   RETURNDTL d
         WHERE  d.LOCATIONCODE = 1 AND d.RESETNO = 1 AND d.GOODSRETURNNO = 1
         AND    d.ITEMCODE = a.ITEMCODE
         AND    UPPER(TRIM(d.UOM)) = UPPER(TRIM(a.ALTERNATEUOMCODE))
       )
WHERE  a.LOCATIONCODE = 1
AND    NVL(a.IS_BASE, 'N') <> 'Y'
AND    EXISTS (
         SELECT 1 FROM RETURNDTL d
         WHERE  d.LOCATIONCODE = 1 AND d.RESETNO = 1 AND d.GOODSRETURNNO = 1
         AND    d.ITEMCODE = a.ITEMCODE
         AND    UPPER(TRIM(d.UOM)) = UPPER(TRIM(a.ALTERNATEUOMCODE))
       );

-- B3. Delete the journal rows created by this duplicate return post.
DELETE FROM ITEMJOURNAL
WHERE  LOCATIONCODE = 1 AND RESETNO = 1
AND    RECEIPTNO = 1
AND    TRANSTYPE = 'PURCHASE_RETURN';

-- B4. Delete the duplicate document lines + header.
DELETE FROM RETURNDTL
WHERE  LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1;

DELETE FROM RETURNHDR
WHERE  LOCATIONCODE = 1 AND RESETNO = 1 AND GOODSRETURNNO = 1;

-- B5. (Optional) Also remove any GL/posting rows for #1, if it had been GL-posted:
-- DELETE FROM TBLPRPOSTINGDTL WHERE LOCATIONCODE=1 AND RESETNO=1 AND GOODSRETURNNO=1;
-- DELETE FROM TBLPRPOSTINGHDR WHERE LOCATIONCODE=1 AND RESETNO=1 AND GOODSRETURNNO=1;

-- ---------------------------------------------------------------------
-- VERIFY with SECTION A again. If correct:
--   COMMIT;
-- else:
--   ROLLBACK;
-- ---------------------------------------------------------------------
