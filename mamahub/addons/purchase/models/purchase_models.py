"""Purchasing addon — lot columns + introspected DB models (:mod:`from_db`)."""
from __future__ import annotations
from addons.core.schema.cols_inventory import ItemLotBalanceCols, ItemLotBinCols, ItemLotCols, ItemLotMovementCols
from addons.core.schema.common_models import TenantTables, from_db
Lot = ItemLotCols
LotBal = ItemLotBalanceCols
LotMov = ItemLotMovementCols
LotBin = ItemLotBinCols
__all__ = ['TenantTables', 'from_db', 'Lot', 'LotBal', 'LotMov', 'LotBin', 'ItemLotCols', 'ItemLotBalanceCols', 'ItemLotMovementCols', 'ItemLotBinCols']
