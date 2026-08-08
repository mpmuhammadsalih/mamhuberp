# Purchase Order, Goods Receipt Note (GRN), and Purchase Invoice

This document maps your VB6 purchase flow to tables and a suggested web implementation.

## Table mapping

| Module | Your tables | Purpose |
|--------|-------------|---------|
| **Purchase Order** | LPOHDR, LPODTL | Order to supplier (LPO = Local Purchase Order). LPOHDR: LocationCode, ResetNo, LPONo, LPODate, SupplierCode, Discount, LPOAmount, Remarks, DelFlag, LRFLAG ('L'=open, 'R'=received). LPODTL: ItemCode, UOM, Quantity, Rate, Store, Bonus, Discount, OtherCharge, etc. |
| **Goods Receipt Note (GRN)** | ReceiptHdr, ReceiptDtl | Receive goods (from VB Receipt form). ReceiptHdr: LocationCode, ReceiptNo, ResetNo, ReceiptDate, SupplierCode, InvoiceNo, InvoiceDate, Discount, InvoiceAmount, Remarks, LpoNo, vatamount, totalamount, etc. ReceiptDtl: ItemCode, UnitOfMeasurement, Quantity, Rate, Store, Bonus, Discount, OtherCharge, Amount, VAT, totalamount, baseqty, landingcost, etc. |
| **Purchase Invoice** | PURCHASEINVOICEHDR, PURCHASEINVOICEDTL | Book supplier invoice (new tables – see `scripts/create_purchase_invoice_tables.sql`). |

## Flow

1. **Purchase Order** – Create LPO (LPOHDR + LPODTL). LRFLAG = 'L'.
2. **GRN** – Receive against LPO or direct: insert ReceiptHdr + ReceiptDtl, update ItemMaster stock/cost, optionally set LPOHDR.LRFLAG = 'R' when LPO fully received.
3. **Purchase Invoice** – When supplier invoice is received: create PURCHASEINVOICEHDR (link to ReceiptNo/LpoNo if needed) and PURCHASEINVOICEDTL; can copy from ReceiptHdr/ReceiptDtl or enter separately.

## Purchase Invoice tables (created by script)

- **PURCHASEINVOICEHDR**: LocationCode, ResetNo, PurchaseInvoiceNo, InvoiceDate, SupplierCode, SupplierInvoiceNo, SupplierInvoiceDate, ReceiptNo, ReceiptResetNo, LpoNo, SubTotal, Discount, VATAmount, TotalAmount, CurrencyCode, ExchangeRate, Remarks, DelFlag, CreatedBy, CreatedDate, DueDate, etc.
- **PURCHASEINVOICEDTL**: LocationCode, ResetNo, PurchaseInvoiceNo, LineNo, ItemCode, UnitOfMeasurement, Quantity, Rate, Amount, Bonus, Discount, OtherCharge, VATPercent, VATAmount, TotalAmount, ReceiptNo, Store, BaseQty, LandingCost, etc.

Run the DDL in `scripts/create_purchase_invoice_tables.sql` in your Oracle database to create these tables.

## Web implementation (suggested)

1. **Purchase Order** – New blueprint (e.g. `purchase_order.py`): list LPOHDR, create/edit LPO (LPOHDR + LPODTL), open from LPO for GRN.
2. **Goods Receipt Note** – New blueprint (e.g. `goods_receipt.py`): replicate VB Receipt flow – ReceiptHdr (supplier, date, invoice no/date, discount, amount) + ReceiptDtl grid (item, UOM, qty, rate, store, bonus, discount, other charge, amount, VAT, total); get next ReceiptNo from max(ReceiptNo); save ReceiptHdr + ReceiptDtl, update ItemMaster (currentstock, store1/store2/..., costprice, averagecost, landingcost); optional “Load from LPO” (query LPODTL by LPONo and fill grid).
3. **Purchase Invoice** – New blueprint (e.g. `purchase_invoice.py`): list PURCHASEINVOICEHDR, create/edit Purchase Invoice (header + detail); optional “Load from GRN” by ReceiptNo to copy lines from ReceiptDtl into PURCHASEINVOICEDTL.

Use the same patterns as Salesman Receipt / Temporary Collection: location from session, transaction date from TBLTRANSACTIONDATE (transactioncode = 1 for receipt date in VB openDate), detect table/column names (e.g. ReceiptHdr/ReceiptDtl, LPOHDR/LPODTL) with `_detect_table` / `_detect_column`, and run DDL once to create the Purchase Invoice tables before using them in the app.
