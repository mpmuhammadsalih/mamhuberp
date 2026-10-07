"""
Resolve ERP table/column names for AI forecasting (Oracle-safe, multi-schema).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from db import _detect_column, _detect_table, _get_table_columns, _table_exists

BILL_HDR_ALIAS = 'bh'
BILL_DTL_ALIAS = 'bd'
DEFAULT_BILL_RESET_NO = int(os.environ.get('AI_FORECAST_BILL_RESET_NO', '1') or 1)


@dataclass
class ForecastSchema:
    location_code: int
    bill_hdr: Optional[str] = None
    bill_dtl: Optional[str] = None
    receipt_hdr: Optional[str] = None
    receipt_dtl: Optional[str] = None
    lpo_hdr: Optional[str] = None
    lpo_dtl: Optional[str] = None
    item_tbl: Optional[str] = None
    supplier_tbl: Optional[str] = None
    customer_tbl: Optional[str] = None
    cols: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, location_code: int) -> 'ForecastSchema':
        s = cls(location_code=int(location_code or 1))
        s.bill_hdr = _detect_table(['BILLHDRHISTORY', 'billhdrhistory', 'BILLHDR', 'billhdr'])
        s.bill_dtl = _detect_table(['BILLDTLHISTORY', 'billdtlhistory', 'BILLDTL', 'billdtl'])
        s.receipt_hdr = _detect_table(['RECEIPTHDR', 'receipthdr'])
        s.receipt_dtl = _detect_table(['RECEIPTDTL', 'receiptdtl'])
        s.lpo_hdr = _detect_table(['LPOHDR', 'lpohdr'])
        s.lpo_dtl = _detect_table(['LPODTL', 'lpodtl'])
        s.item_tbl = _detect_table(['ITEMMASTERDETAILS', 'itemmasterdetails', 'ITEMMASTER', 'itemmaster'])
        s.supplier_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
        s.customer_tbl = _detect_table(['CUSTOMERS', 'CUSTOMER', 'customer', 'customers'])
        s._detect_cols()
        return s

    def _col(self, table: Optional[str], keys: List[str], alias: str) -> None:
        if not table:
            return
        c = _detect_column(table, keys)
        if c:
            self.cols[alias] = c

    def _detect_cols(self) -> None:
        h, d = self.bill_hdr, self.bill_dtl
        self._col(h, ['BILLNO', 'BILL_NO', 'billno'], 'h_billno')
        self._col(h, ['BILLDATE', 'BILL_DATE', 'billdate', 'TRANDATE'], 'h_billdate')
        self._col(h, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'], 'h_loc')
        self._col(h, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode', 'CUSTCODE', 'CUST_CODE'], 'h_customer')
        self._col(h, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'customername'], 'h_custname')
        self._col(h, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_BILL_AMOUNT', 'netbillamount'], 'h_net')
        self._col(h, ['RESETNO', 'RESET_NO', 'resetno'], 'h_reset')
        self._col(h, ['CANCELFLAG', 'CANCEL_FLAG', 'cancelflag'], 'h_cancel')
        self._col(h, ['DELFLAG', 'DEL_FLAG', 'delflag'], 'h_del')
        self._col(h, ['BILLSTATUS', 'BILL_STATUS', 'billstatus'], 'h_status')
        self._col(h, ['RETURNFLAG', 'returnflag'], 'h_return')
        self._col(d, ['BILLNO', 'BILL_NO', 'billno'], 'd_billno')
        self._col(d, ['ITEMCODE', 'ITEM_CODE', 'itemcode'], 'd_item')
        self._col(d, ['QUANTITY', 'quantity'], 'd_qty')
        self._col(d, ['RATE', 'rate'], 'd_rate')
        self._col(d, ['ITDISC', 'itdisc', 'DISCOUNT', 'discount'], 'd_disc')
        self._col(d, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'], 'd_loc')
        self._col(d, ['RESETNO', 'RESET_NO', 'resetno'], 'd_reset')
        self._col(d, ['AMOUNT', 'amount', 'LINEAMOUNT', 'lineamount'], 'd_amt')

        rh, rd = self.receipt_hdr, self.receipt_dtl
        self._col(rh, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'], 'rh_no')
        self._col(rh, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'], 'rh_date')
        self._col(rh, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'], 'rh_sup')
        self._col(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'], 'rh_loc')
        self._col(rh, ['LPONO', 'LPO_NO', 'lpono'], 'rh_lpo')
        self._col(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'], 'rh_del')
        self._col(rd, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'], 'rd_no')
        self._col(rd, ['ITEMCODE', 'ITEM_CODE', 'itemcode'], 'rd_item')
        self._col(rd, ['QUANTITY', 'quantity'], 'rd_qty')
        self._col(rd, ['RATE', 'rate'], 'rd_rate')

        lh, ld = self.lpo_hdr, self.lpo_dtl
        self._col(lh, ['LPONO', 'LPO_NO', 'lpono'], 'lh_lpo')
        self._col(lh, ['LPODATE', 'LPO_DATE', 'lpodate'], 'lh_date')
        self._col(lh, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'], 'lh_sup')
        self._col(lh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'], 'lh_loc')
        self._col(lh, ['DELFLAG', 'DEL_FLAG', 'delflag'], 'lh_del')
        self._col(ld, ['LPONO', 'LPO_NO', 'lpono'], 'ld_lpo')
        self._col(ld, ['ITEMCODE', 'ITEM_CODE', 'itemcode'], 'ld_item')
        self._col(ld, ['QUANTITY', 'INQUANTITY', 'INQUANTTITY', 'quantity'], 'ld_qty')

        im = self.item_tbl
        self._col(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'], 'im_item')
        self._col(im, ['ITEMNAME', 'ITEM_NAME', 'itemname'], 'im_name')
        self._col(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'], 'im_loc')
        self._col(im, ['SUPCODE', 'SUPPLIERCODE', 'SUPPLIER_CODE', 'supcode'], 'im_sup')
        self._col(im, ['REORDERLEVEL', 'REORDER_LEVEL', 'reorderlevel'], 'im_reorder')
        self._col(im, ['MAXIMUMLEVEL', 'MAXIMUM_LEVEL', 'maximumlevel'], 'im_max')
        self._col(im, ['CURRENTSTOCK', 'CURRENT_STOCK', 'currentstock'], 'im_stock')
        self._col(im, ['COSTPRICE', 'COST_PRICE', 'costprice'], 'im_cost')
        self._col(im, ['RETAILPRICE', 'RETAIL_PRICE', 'retailprice'], 'im_retail')
        self._col(im, ['ITEMFLAG', 'itemflag', 'ACTIVE', 'active'], 'im_flag')

        sup = self.supplier_tbl
        self._col(sup, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'], 'sup_code')
        self._col(sup, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername'], 'sup_name')

        cust = self.customer_tbl
        self._col(cust, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE'], 'cust_code')
        self._col(cust, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'], 'cust_name')

    def _hdr_has_col(self, col_key: str, candidates: List[str]) -> Optional[str]:
        """Return column name only if it exists on the resolved bill header table."""
        tbl = self.bill_hdr
        if not tbl:
            return None
        stored = self.cols.get(col_key)
        if stored:
            try:
                cols = {str(c).upper() for c in _get_table_columns(tbl) or []}
            except Exception:
                cols = set()
            if stored.upper() in cols:
                return stored
        return _detect_column(tbl, candidates)

    def bill_join_sql(
        self,
        hdr_alias: str = BILL_HDR_ALIAS,
        dtl_alias: str = BILL_DTL_ALIAS,
    ) -> Optional[str]:
        if not self.bill_hdr or not self.bill_dtl:
            return None
        hb, db = self.cols.get('h_billno'), self.cols.get('d_billno')
        if not hb or not db:
            return None
        join = f'{dtl_alias}.{db} = {hdr_alias}.{hb}'
        hl, dl = self.cols.get('h_loc'), self.cols.get('d_loc')
        if hl and dl:
            join += f' AND {dtl_alias}.{dl} = {hdr_alias}.{hl}'
        hr, dr = self.cols.get('h_reset'), self.cols.get('d_reset')
        if hr and dr:
            join += f' AND {dtl_alias}.{dr} = {hdr_alias}.{hr}'
        return join

    def bill_query_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {'loc': self.location_code}
        if self.cols.get('h_reset'):
            params['rn'] = DEFAULT_BILL_RESET_NO
        if extra:
            params.update(extra)
        return params

    def bill_amount_expr(self, hdr_alias: str = BILL_HDR_ALIAS, dtl_alias: str = BILL_DTL_ALIAS) -> str:
        """Header net amount per bill, else sum of line amounts."""
        net = self.cols.get('h_net')
        qty = self.cols.get('d_qty')
        rate = self.cols.get('d_rate')
        amt = self.cols.get('d_amt')
        disc = self.cols.get('d_disc')
        if net:
            return f'NVL({hdr_alias}.{net}, 0)'
        line = f'NVL({dtl_alias}.{qty}, 0) * NVL({dtl_alias}.{rate}, 0)'
        if amt:
            line = f'NVL({dtl_alias}.{amt}, {line})'
        if disc:
            line = f'NVL({dtl_alias}.{qty}, 0) * (NVL({dtl_alias}.{rate}, 0) - NVL({dtl_alias}.{disc}, 0))'
        return f'SUM({line})'

    def bill_cancel_filter(self, alias: str = BILL_HDR_ALIAS) -> str:
        parts: List[str] = []
        if not self.bill_hdr:
            return '1=1'
        cancel = self._hdr_has_col('h_cancel', ['CANCELFLAG', 'CANCEL_FLAG', 'cancelflag'])
        if cancel:
            parts.append(f"NVL({alias}.{cancel},'N') <> 'Y'")
        delc = self._hdr_has_col('h_del', ['DELFLAG', 'DEL_FLAG', 'delflag'])
        if delc:
            parts.append(f"NVL({alias}.{delc},'N') <> 'Y'")
        status = self._hdr_has_col('h_status', ['BILLSTATUS', 'BILL_STATUS', 'billstatus'])
        if status:
            parts.append(
                f"({alias}.{status} IS NULL OR UPPER(TRIM({alias}.{status})) NOT IN ('V', 'VOID', 'C'))"
            )
        return ' AND '.join(parts) if parts else '1=1'

    def bill_loc_filter(self, hdr_alias: str = BILL_HDR_ALIAS, dtl_alias: str = BILL_DTL_ALIAS) -> str:
        hl, dl = self.cols.get('h_loc'), self.cols.get('d_loc')
        if hl and dl:
            return f'({hdr_alias}.{hl} = :loc OR {dtl_alias}.{dl} = :loc)'
        if hl:
            return f'{hdr_alias}.{hl} = :loc'
        if dl:
            return f'{dtl_alias}.{dl} = :loc'
        return '1=1'

    def bill_reset_filter(self, hdr_alias: str = BILL_HDR_ALIAS, dtl_alias: str = BILL_DTL_ALIAS) -> str:
        hr, dr = self.cols.get('h_reset'), self.cols.get('d_reset')
        parts: List[str] = []
        if hr:
            parts.append(f'{hdr_alias}.{hr} = :rn')
        if dr:
            parts.append(f'{dtl_alias}.{dr} = :rn')
        return ' AND '.join(parts) if parts else '1=1'

    def item_active_filter(self, alias: str = 'im') -> str:
        flag = self.cols.get('im_flag')
        if flag:
            return f"(NVL({alias}.{flag},'A') NOT IN ('I','N','D','0'))"
        return '1=1'

    def has_sales(self) -> bool:
        return bool(self.bill_hdr and self.bill_dtl and self.cols.get('h_billdate') and self.cols.get('d_qty'))
