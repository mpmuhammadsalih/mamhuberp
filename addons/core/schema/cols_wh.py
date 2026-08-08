"""Column identifiers aligned with DDL in ``db.ensure_warehouse_storage_table`` / bin stock / transfers."""
from __future__ import annotations
from addons.core.schema.tenant_tables import TenantTables

class WarehouseMasterCols:
    """``WAREHOUSE_MASTER`` — warehouse / store sites per branch."""
    TABLE = 'WAREHOUSE_MASTER'
    WAREHOUSE_ID = 'WAREHOUSE_ID'
    WAREHOUSE_CODE = 'WAREHOUSE_CODE'
    WAREHOUSE_NAME = 'WAREHOUSE_NAME'
    LOCATIONCODE = 'LOCATIONCODE'
    WAREHOUSE_TYPE = 'WAREHOUSE_TYPE'
    ADDRESS = 'ADDRESS'
    CONTACT_PERSON = 'CONTACT_PERSON'
    PHONE_NO = 'PHONE_NO'
    ALLOW_NEGATIVE_STOCK = 'ALLOW_NEGATIVE_STOCK'
    BATCH_ENABLED = 'BATCH_ENABLED'
    BIN_ENABLED = 'BIN_ENABLED'
    IS_ACTIVE = 'IS_ACTIVE'
    CREATED_BY = 'CREATED_BY'
    CREATED_DATE = 'CREATED_DATE'
    UPDATED_BY = 'UPDATED_BY'
    UPDATED_DATE = 'UPDATED_DATE'
    REMARKS = 'REMARKS'

class WarehouseStorageCols:
    """``WAREHOUSE_STORAGE`` — shelf / bin / rack nodes."""
    TABLE = TenantTables.warehouse_storage
    STORAGE_ID = 'STORAGE_ID'
    WAREHOUSE_ID = 'WAREHOUSE_ID'
    LOCATIONCODE = 'LOCATIONCODE'
    STORAGE_TYPE = 'STORAGE_TYPE'
    CODE = 'CODE'
    NAME = 'NAME'
    STATUS = 'STATUS'
    REMARKS = 'REMARKS'
    PARENT_STORAGE_ID = 'PARENT_STORAGE_ID'
    CREATED_AT = 'CREATED_AT'

class WarehouseStockCols:
    """``WAREHOUSE_STOCK`` — quantity per warehouse site + item (branch-level)."""
    TABLE = TenantTables.warehouse_stock
    LOCATIONCODE = 'LOCATIONCODE'
    WAREHOUSE_ID = 'WAREHOUSE_ID'
    ITEMCODE = 'ITEMCODE'
    QTY = 'QTY'
    UPDATED_AT = 'UPDATED_AT'
    UPDATED_BY = 'UPDATED_BY'

class BinStockCols:
    """``BIN_STOCK`` — quantity per bin + item."""
    TABLE = TenantTables.bin_stock
    STORAGE_ID = 'STORAGE_ID'
    ITEMCODE = 'ITEMCODE'
    QTY = 'QTY'
    WAREHOUSE_ID = 'WAREHOUSE_ID'
    UPDATED_AT = 'UPDATED_AT'
    UPDATED_BY = 'UPDATED_BY'

class StockBinTransferHdrCols:
    """``STOCK_BIN_TRANSFER_HDR``."""
    TABLE = TenantTables.stock_bin_transfer_hdr
    TRANSFER_ID = 'TRANSFER_ID'
    WAREHOUSE_ID = 'WAREHOUSE_ID'
    FROM_STORAGE_ID = 'FROM_STORAGE_ID'
    TO_STORAGE_ID = 'TO_STORAGE_ID'
    REMARKS = 'REMARKS'
    STATUS = 'STATUS'
    CREATED_AT = 'CREATED_AT'
    CREATED_BY = 'CREATED_BY'

class StockBinTransferDtlCols:
    """``STOCK_BIN_TRANSFER_DTL``."""
    TABLE = TenantTables.stock_bin_transfer_dtl
    TRANSFER_ID = 'TRANSFER_ID'
    LINE_NO = 'LINE_NO'
    ITEMCODE = 'ITEMCODE'
    QTY = 'QTY'
__all__ = ['WarehouseMasterCols', 'WarehouseStorageCols', 'WarehouseStockCols', 'BinStockCols', 'StockBinTransferHdrCols', 'StockBinTransferDtlCols']
