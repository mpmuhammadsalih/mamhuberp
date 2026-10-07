"""Item / batch / lot identifiers aligned with DDL in ``db.ensure_item_lot_tables``."""
from __future__ import annotations
from addons.core.schema.tenant_tables import TenantTables

class ItemLotCols:
    TABLE = TenantTables.item_lot
    LOT_ID = 'LOT_ID'
    LOCATIONCODE = 'LOCATIONCODE'
    ITEMCODE = 'ITEMCODE'
    BATCH_NO = 'BATCH_NO'
    MFG_DATE = 'MFG_DATE'
    EXPIRY_DATE = 'EXPIRY_DATE'
    SUPPLIERCODE = 'SUPPLIERCODE'
    RECEIPT_NO = 'RECEIPT_NO'
    RECEIPT_LINE = 'RECEIPT_LINE'
    REMARKS = 'REMARKS'
    CREATED_AT = 'CREATED_AT'
    UNIT_COST = 'UNIT_COST'

class ItemLotBalanceCols:
    TABLE = TenantTables.item_lot_balance
    LOT_ID = 'LOT_ID'
    QTY = 'QTY'

class ItemLotMovementCols:
    TABLE = TenantTables.item_lot_movement
    MOV_ID = 'MOV_ID'
    LOT_ID = 'LOT_ID'
    QTY = 'QTY'
    KIND = 'KIND'
    REF_TYPE = 'REF_TYPE'
    REF_NO = 'REF_NO'
    REF_LINE = 'REF_LINE'
    REMARKS = 'REMARKS'
    AT_TS = 'AT_TS'

class ItemLotBinCols:
    TABLE = TenantTables.item_lot_bin
    LOT_ID = 'LOT_ID'
    STORAGE_ID = 'STORAGE_ID'
    QTY = 'QTY'
__all__ = ['ItemLotCols', 'ItemLotBalanceCols', 'ItemLotMovementCols', 'ItemLotBinCols']
