"""Physical table identifiers for tenant/auth DB DDL defined in ``db.py``.

Import :class:`TenantTables` from addons instead of hard-coding literals in controllers.

To add a new table:
1. Declare ``MY_TABLE = "NAME"`` in ``db.py`` (and DDL helpers).
2. Import ``MY_TABLE`` here and attach to :class:`TenantTables`.
"""
from __future__ import annotations
from types import SimpleNamespace
from db import AP_ALLOC_TABLE, AR_ALLOC_TABLE, BIN_STOCK_TABLE, CHART_OF_ACCOUNTS_TABLE, CHAT_CONVERSATIONS_TABLE, CHAT_MESSAGES_TABLE, CHAT_PARTICIPANTS_TABLE, CHAT_REACTIONS_TABLE, CHAT_TYPING_TABLE, GL_DTL_TABLE, GL_HDR_TABLE, ITEM_LOT_BIN_TABLE, ITEM_LOT_BALANCE_TABLE, ITEM_LOT_MOVEMENT_TABLE, ITEM_LOT_TABLE, LOCATIONS_TABLE, PDC_TABLE, STOCK_BIN_TRANSFER_DTL_TABLE, STOCK_BIN_TRANSFER_HDR_TABLE, SUPPLIER_TABLE, WAREHOUSE_STOCK_TABLE, WAREHOUSE_STORAGE_TABLE
TenantTables = SimpleNamespace(locations=LOCATIONS_TABLE, supplier=SUPPLIER_TABLE, chart_of_accounts=CHART_OF_ACCOUNTS_TABLE, warehouse_storage=WAREHOUSE_STORAGE_TABLE, warehouse_stock=WAREHOUSE_STOCK_TABLE, bin_stock=BIN_STOCK_TABLE, stock_bin_transfer_hdr=STOCK_BIN_TRANSFER_HDR_TABLE, stock_bin_transfer_dtl=STOCK_BIN_TRANSFER_DTL_TABLE, item_lot=ITEM_LOT_TABLE, item_lot_balance=ITEM_LOT_BALANCE_TABLE, item_lot_movement=ITEM_LOT_MOVEMENT_TABLE, item_lot_bin=ITEM_LOT_BIN_TABLE, gl_voucher_hdr=GL_HDR_TABLE, gl_voucher_dtl=GL_DTL_TABLE, ap_supplier_payment_alloc=AP_ALLOC_TABLE, ar_customer_payment_alloc=AR_ALLOC_TABLE, pdc=PDC_TABLE, chat_conversations=CHAT_CONVERSATIONS_TABLE, chat_participants=CHAT_PARTICIPANTS_TABLE, chat_messages=CHAT_MESSAGES_TABLE, chat_reactions=CHAT_REACTIONS_TABLE, chat_typing=CHAT_TYPING_TABLE)
__all__ = ['TenantTables']
