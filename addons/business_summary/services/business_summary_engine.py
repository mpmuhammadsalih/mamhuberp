"""Daily Business Summary dashboard — KPIs, charts, tables (tenant DB)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import (
    GL_DTL_TABLE,
    GL_HDR_TABLE,
    _detect_column,
    _detect_table,
    _get_scalar,
    _get_table_columns,
    _merge_pos_shift_tender_totals,
    _safe_rows,
    ensure_gl_tables,
    get_accounts_payable_summary,
    get_accounts_receivable_summary,
    get_locations_list,
    get_profit_and_loss_report,
    list_pos_tender_types,
)

from addons.reports.gross_margin_logic import build_gross_margin_dashboard, get_gross_margin_filter_options


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_date(raw: Any, fallback: date) -> date:
    s = str(raw or '').strip()[:10]
    if not s:
        return fallback
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return fallback


def _sql_top_n(query: str, limit: int) -> str:
    """Limit rows using ROWNUM (Oracle 11g compatible; avoids FETCH FIRST ORA-00933)."""
    n = max(1, min(int(limit or 1), 5000))
    q = (query or '').strip().rstrip(';')
    return f'SELECT * FROM (\n{q}\n) WHERE ROWNUM <= {n}'


def parse_business_summary_filters(raw: Dict[str, Any]) -> Dict[str, Any]:
    today = date.today()
    d_from = _parse_date(raw.get('date_from'), today.replace(day=1))
    d_to = _parse_date(raw.get('date_to'), today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    branch = str(raw.get('branch') or raw.get('locationcode') or '').strip()
    loc = int(branch) if branch.isdigit() else None
    return {
        'date_from': d_from.isoformat(),
        'date_to': d_to.isoformat(),
        'branch': loc,
        'warehouse': str(raw.get('warehouse') or '').strip(),
        'category_code': str(raw.get('category_code') or '').strip(),
        'brand_code': str(raw.get('brand_code') or '').strip(),
        'customer_code': str(raw.get('customer_code') or '').strip(),
        'supplier_code': str(raw.get('supplier_code') or '').strip(),
        'salesman_code': str(raw.get('salesman_code') or '').strip(),
    }


def get_business_summary_filter_options(location_code: Optional[int] = None) -> Dict[str, Any]:
    opts = get_gross_margin_filter_options(location_code)
    branches = get_locations_list() or []
    suppliers: List[Dict[str, Any]] = []
    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    if sup_tbl:
        code_col = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
        name_col = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME', 'suppliername'])
        if code_col:
            rows = _safe_rows(
                _sql_top_n(
                    f'SELECT {code_col} AS code, {name_col or code_col} AS name FROM {sup_tbl} ORDER BY 2',
                    500,
                ),
                {},
            )
            suppliers = [{'code': r.get('code'), 'name': r.get('name') or ''} for r in rows]
    return {
        'branches': branches,
        'warehouses': opts.get('warehouses') or [],
        'categories': opts.get('categories') or [],
        'brands': opts.get('brands') or [],
        'customers': opts.get('customers') or [],
        'salesmen': opts.get('salesmen') or [],
        'suppliers': suppliers,
    }


_SALES_RESET_NO = 1
_GRN_RESET_NO = 1
_sales_ctx_cache: Optional[Dict[str, Any]] = None


def _reset_sales_ctx() -> None:
    global _sales_ctx_cache
    _sales_ctx_cache = None


def _resolve_sales_hdr_dtl() -> Tuple[str, str]:
    """Prefer BILLHDRHISTORY when present (matches mobile dashboard / posted sales)."""
    hdr = _detect_table(['BILLHDRHISTORY', 'billhdrhistory'])
    dtl = _detect_table(['BILLDTLHISTORY', 'billdtlhistory'])
    if hdr and dtl:
        return hdr, dtl
    hdr = _detect_table(['BILLHDR', 'billhdr'])
    dtl = _detect_table(['BILLDTL', 'billdtl'])
    if hdr and dtl:
        return hdr, dtl
    hdr = _detect_table(['BILLHDRHISTORY', 'billhdrhistory'])
    dtl = _detect_table(['BILLDTLHISTORY', 'billdtlhistory'])
    return hdr or '', dtl or ''


def _get_sales_ctx() -> Dict[str, Any]:
    global _sales_ctx_cache
    if _sales_ctx_cache is not None:
        return _sales_ctx_cache
    hdr, dtl = _resolve_sales_hdr_dtl()
    ctx: Dict[str, Any] = {'hdr': hdr, 'dtl': dtl, 'valid': bool(hdr)}
    if not hdr:
        _sales_ctx_cache = ctx
        return ctx
    ctx['date_col'] = _detect_column(hdr, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
    ctx['amt_col'] = _detect_column(hdr, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
    ctx['loc_col'] = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    ctx['cust_col'] = _detect_column(hdr, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE'])
    ctx['sm_col'] = _detect_column(hdr, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    ctx['type_col'] = _detect_column(hdr, ['BILLTYPE', 'BILL_TYPE', 'billtype'])
    ctx['no_col'] = _detect_column(hdr, ['BILLNO', 'BILL_NO', 'billno'])
    ctx['del_col'] = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    ctx['status_col'] = _detect_column(hdr, ['BILLSTATUS', 'billstatus'])
    ctx['reset_col'] = _detect_column(hdr, ['RESETNO', 'resetno'])
    ctx['valid'] = bool(ctx.get('date_col') and ctx.get('amt_col'))
    if dtl:
        ctx['d_bill'] = _detect_column(dtl, ['BILLNO', 'BILL_NO', 'billno'])
        ctx['d_loc'] = _detect_column(dtl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        ctx['d_reset'] = _detect_column(dtl, ['RESETNO', 'resetno'])
        ctx['d_item'] = _detect_column(dtl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
        ctx['d_amt'] = _detect_column(dtl, ['AMOUNT', 'LINEAMOUNT', 'lineamount', 'NETAMOUNT'])
        ctx['d_qty'] = _detect_column(dtl, ['QUANTITY', 'quantity', 'QTY', 'BILLQTY'])
        ctx['d_rate'] = _detect_column(dtl, ['RATE', 'rate', 'SELLRATE'])
    _sales_ctx_cache = ctx
    return ctx


def _sales_amt_expr(ctx: Dict[str, Any]) -> str:
    col = ctx.get('amt_col')
    if not col:
        return '0'
    return f'NVL(bh.{col}, 0)'


def _sales_line_amt_expr(ctx: Dict[str, Any]) -> str:
    if ctx.get('d_amt'):
        return f'NVL(bd.{ctx["d_amt"]}, 0)'
    if ctx.get('d_qty') and ctx.get('d_rate'):
        return f'NVL(bd.{ctx["d_qty"]}, 0) * NVL(bd.{ctx["d_rate"]}, 0)'
    return '0'


def _sales_hdr_dtl_join(ctx: Dict[str, Any]) -> str:
    parts = [f'bh.{ctx["no_col"]} = bd.{ctx["d_bill"]}']
    if ctx.get('loc_col') and ctx.get('d_loc'):
        parts.append(f'bh.{ctx["loc_col"]} = bd.{ctx["d_loc"]}')
    if ctx.get('reset_col') and ctx.get('d_reset'):
        parts.append(f'bh.{ctx["reset_col"]} = bd.{ctx["d_reset"]}')
    return ' AND '.join(parts)


def _billhdr_loc_filter(ctx: Dict[str, Any], loc: Optional[int]) -> Tuple[str, Dict[str, Any]]:
    if loc is None or not ctx.get('loc_col'):
        return '', {}
    return f' AND bh.{ctx["loc_col"]} = :loc ', {'loc': int(loc)}


def _billhdr_filters(
    ctx: Dict[str, Any],
    d_from: date,
    d_to: date,
    loc: Optional[int],
    extra_where: str = '',
    extra_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    if not ctx.get('valid'):
        return ' AND 1=0 ', {}
    loc_sql, loc_params = _billhdr_loc_filter(ctx, loc)
    params: Dict[str, Any] = {'d_from': d_from, 'd_to': d_to, **loc_params}
    if extra_params:
        params.update(extra_params)
    std = ''
    if ctx.get('reset_col'):
        std += f' AND bh.{ctx["reset_col"]} = :srn '
        params['srn'] = _SALES_RESET_NO
    if ctx.get('del_col'):
        std += f" AND NVL(bh.{ctx['del_col']}, 'N') = 'N' "
    if ctx.get('status_col'):
        std += f" AND (bh.{ctx['status_col']} IS NULL OR UPPER(TRIM(bh.{ctx['status_col']})) <> 'V') "
    where = f"""
        AND TRUNC(bh.{ctx['date_col']}) >= TRUNC(:d_from)
        AND TRUNC(bh.{ctx['date_col']}) <= TRUNC(:d_to)
        {loc_sql}
        {std}
        {extra_where}
    """
    return where, params


def _sum_billhdr(ctx: Dict[str, Any], where: str, params: Dict[str, Any], expr: Optional[str] = None) -> float:
    if not ctx.get('valid'):
        return 0.0
    amt = expr or _sales_amt_expr(ctx)
    q = f'SELECT NVL(SUM({amt}), 0) FROM {ctx["hdr"]} bh WHERE 1=1 {where}'
    return _f(_get_scalar(q, params))


def _count_billhdr(ctx: Dict[str, Any], where: str, params: Dict[str, Any]) -> int:
    if not ctx.get('valid'):
        return 0
    q = f'SELECT COUNT(*) FROM {ctx["hdr"]} bh WHERE 1=1 {where}'
    return int(_get_scalar(q, params) or 0)


def _sales_metrics(filters: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _get_sales_ctx()
    empty = {
        'total_sales': 0.0,
        'sales_return': 0.0,
        'net_sales': 0.0,
        'sales_count': 0,
        'return_count': 0,
        'cash_sales': 0.0,
        'credit_sales': 0.0,
    }
    if not ctx.get('valid'):
        return empty
    d_from = _parse_date(filters['date_from'], date.today())
    d_to = _parse_date(filters['date_to'], date.today())
    loc = filters.get('branch')
    extra = ''
    extra_params: Dict[str, Any] = {}
    if filters.get('customer_code') and ctx.get('cust_col'):
        extra += f' AND bh.{ctx["cust_col"]} = :cust '
        cc = filters['customer_code']
        extra_params['cust'] = int(cc) if str(cc).isdigit() else cc
    if filters.get('salesman_code') and ctx.get('sm_col'):
        extra += f' AND bh.{ctx["sm_col"]} = :sm '
        sm = filters['salesman_code']
        extra_params['sm'] = int(sm) if str(sm).isdigit() else sm
    amt_expr = _sales_amt_expr(ctx)
    base_where, base_params = _billhdr_filters(ctx, d_from, d_to, loc, extra, extra_params)

    pos_where = base_where + f' AND {amt_expr} >= 0 '
    ret_where = base_where + f' AND {amt_expr} < 0 '

    total_sales = _sum_billhdr(ctx, pos_where, base_params)
    sales_return = abs(_sum_billhdr(ctx, ret_where, base_params))
    net_sales = total_sales - sales_return
    sales_count = _count_billhdr(ctx, pos_where, base_params)
    return_count = _count_billhdr(ctx, ret_where, base_params)

    bt_col = ctx.get('type_col')
    if bt_col:
        cash_sales = _sum_billhdr(
            ctx,
            pos_where + f" AND UPPER(NVL(bh.{bt_col}, 'C')) LIKE 'C%'",
            base_params,
        )
        credit_sales = _sum_billhdr(
            ctx,
            pos_where + f" AND UPPER(NVL(bh.{bt_col}, 'C')) NOT LIKE 'C%'",
            base_params,
        )
    else:
        cash_sales = total_sales * 0.6
        credit_sales = total_sales - cash_sales

    return {
        'total_sales': total_sales,
        'sales_return': sales_return,
        'net_sales': net_sales,
        'sales_count': sales_count,
        'return_count': return_count,
        'cash_sales': cash_sales,
        'credit_sales': credit_sales,
    }


def _grn_receipt_filter_ctx(filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Shared RECEIPTHDR/RECEIPTDTL context for GRN value aggregates."""
    d_from = filters['date_from']
    d_to = filters['date_to']
    loc = filters.get('branch')
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    if not rh:
        return None
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    r_date = _detect_column(rh, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    r_loc = _detect_column(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    r_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    r_reset = _detect_column(rh, ['RESETNO', 'RESET_NO', 'resetno'])
    r_no = _detect_column(rh, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    r_sup = _detect_column(rh, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    r_inv_amt = _detect_column(rh, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount'])
    r_hdr_amt = _detect_column(rh, ['RECEIPTAMOUNT', 'receiptamount', 'NETAMOUNT', 'GRNAMOUNT'])
    if not r_date or not r_no:
        return None
    where = [
        f'TRUNC(h.{r_date}) >= TO_DATE(:df, \'YYYY-MM-DD\')',
        f'TRUNC(h.{r_date}) <= TO_DATE(:dt, \'YYYY-MM-DD\')',
    ]
    params: Dict[str, Any] = {'df': d_from, 'dt': d_to}
    if loc and r_loc:
        where.append(f'h.{r_loc} = :loc')
        params['loc'] = int(loc)
    if r_del:
        where.append(f"NVL(h.{r_del}, 'N') = 'N'")
    if r_reset:
        where.append(f'h.{r_reset} = :rn')
        params['rn'] = _GRN_RESET_NO
    if filters.get('supplier_code') and r_sup:
        sup = filters['supplier_code']
        where.append(f'h.{r_sup} = :sup')
        params['sup'] = int(sup) if str(sup).isdigit() else sup
    ctx: Dict[str, Any] = {
        'rh': rh,
        'rd': rd,
        'w': ' AND '.join(where),
        'params': params,
        'r_date': r_date,
        'r_no': r_no,
        'line_amt': None,
        'join_sql': None,
        'hdr_amt_col': r_inv_amt or r_hdr_amt,
    }
    if rd:
        d_loc = _detect_column(rd, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        d_no = _detect_column(rd, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
        d_reset = _detect_column(rd, ['RESETNO', 'RESET_NO', 'resetno'])
        d_qty = _detect_column(rd, ['QUANTITY', 'QTY', 'quantity', 'RECEIPTQTY'])
        d_rate = _detect_column(rd, ['RATE', 'rate', 'COSTPRICE'])
        d_disc = _detect_column(rd, ['DISCOUNT', 'discount', 'ITDISC', 'LINEDISCOUNT'])
        d_amt = _detect_column(rd, ['AMOUNT', 'LINEAMOUNT', 'lineamount', 'NETAMOUNT'])
        if d_no:
            join_parts = [f'd.{d_no} = h.{r_no}']
            if d_loc and r_loc:
                join_parts.append(f'd.{d_loc} = h.{r_loc}')
            if d_reset and r_reset:
                join_parts.append(f'd.{d_reset} = h.{r_reset}')
            ctx['join_sql'] = ' AND '.join(join_parts)
            if d_amt:
                ctx['line_amt'] = f'ABS(NVL(d.{d_amt}, 0))'
            elif d_qty and d_rate:
                disc_expr = f' - NVL(d.{d_disc}, 0)' if d_disc else ''
                ctx['line_amt'] = (
                    f'ABS(GREATEST(NVL(d.{d_qty}, 0) * NVL(d.{d_rate}, 0){disc_expr}, 0))'
                )
            else:
                ctx['line_amt'] = '0'
    return ctx


def _grn_receipt_totals(filters: Dict[str, Any]) -> Tuple[float, int]:
    """Goods received (GRN) amount and receipt count for the filtered period."""
    ctx = _grn_receipt_filter_ctx(filters)
    if not ctx:
        return 0.0, 0
    rh = ctx['rh']
    w = ctx['w']
    params = ctx['params']
    cnt = int(_get_scalar(f'SELECT COUNT(*) FROM {rh} h WHERE {w}', params) or 0)
    if ctx.get('line_amt') and ctx.get('join_sql') and ctx.get('rd'):
        amt = _f(_get_scalar(
            f"""SELECT NVL(SUM({ctx['line_amt']}), 0)
                FROM {rh} h
                JOIN {ctx['rd']} d ON {ctx['join_sql']}
                WHERE {w}""",
            params,
        ))
    elif ctx.get('hdr_amt_col'):
        amt = _f(_get_scalar(
            f"SELECT NVL(SUM(h.{ctx['hdr_amt_col']}), 0) FROM {rh} h WHERE {w}",
            params,
        ))
    else:
        amt = 0.0
    return amt, cnt


def _grn_receipt_daily_trend(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    ctx = _grn_receipt_filter_ctx(filters)
    if not ctx:
        return []
    rh = ctx['rh']
    w = ctx['w']
    params = ctx['params']
    r_date = ctx['r_date']
    if ctx.get('line_amt') and ctx.get('join_sql') and ctx.get('rd'):
        rows = _safe_rows(
            f"""SELECT TRUNC(h.{r_date}) AS dt, NVL(SUM({ctx['line_amt']}), 0) AS amt
                FROM {rh} h
                JOIN {ctx['rd']} d ON {ctx['join_sql']}
                WHERE {w}
                GROUP BY TRUNC(h.{r_date}) ORDER BY 1""",
            params,
        )
    elif ctx.get('hdr_amt_col'):
        rows = _safe_rows(
            f"""SELECT TRUNC(h.{r_date}) AS dt, NVL(SUM(h.{ctx['hdr_amt_col']}), 0) AS amt
                FROM {rh} h WHERE {w}
                GROUP BY TRUNC(h.{r_date}) ORDER BY 1""",
            params,
        )
    else:
        return []
    out = []
    for r in rows:
        dt = r.get('dt')
        out.append({
            'date': dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10],
            'amount': round(_f(r.get('amt')), 2),
        })
    return out


def _purchase_metrics(filters: Dict[str, Any]) -> Dict[str, Any]:
    d_from = filters['date_from']
    d_to = filters['date_to']
    loc = filters.get('branch')
    hdr = _detect_table(['LPOHDR', 'lpohdr'])
    total = 0.0
    cnt = 0
    if hdr:
        h_date = _detect_column(hdr, ['LPODATE', 'LPO_DATE'])
        h_amt = _detect_column(hdr, ['LPOAMOUNT', 'LPO_AMOUNT', 'NETAMOUNT', 'netamount']) or 'LPOAMOUNT'
        h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE'])
        h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE'])
        h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG'])
        if h_date:
            where = [
                f"TRUNC(h.{h_date}) >= TO_DATE(:df, 'YYYY-MM-DD')",
                f"TRUNC(h.{h_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')",
            ]
            params: Dict[str, Any] = {'df': d_from, 'dt': d_to}
            if loc and h_loc:
                where.append(f'h.{h_loc} = :loc')
                params['loc'] = int(loc)
            if h_del:
                where.append(f"NVL(h.{h_del}, 'N') = 'N'")
            if filters.get('supplier_code') and h_sup:
                where.append(f'h.{h_sup} = :sup')
                params['sup'] = int(filters['supplier_code']) if str(filters['supplier_code']).isdigit() else filters['supplier_code']
            w = ' AND '.join(where)
            total = _f(_get_scalar(f'SELECT NVL(SUM(h.{h_amt}), 0) FROM {hdr} h WHERE {w}', params))
            cnt = int(_get_scalar(f'SELECT COUNT(*) FROM {hdr} h WHERE {w}', params) or 0)

    purchase_source = 'lpo'
    if total <= 0 and cnt <= 0:
        grn_amt, grn_cnt = _grn_receipt_totals(filters)
        if grn_amt > 0 or grn_cnt > 0:
            total = grn_amt
            cnt = grn_cnt
            purchase_source = 'grn'

    ret_hdr = _detect_table(['RETURNHDR', 'returnhdr'])
    ret_amt = 0.0
    ret_cnt = 0
    if ret_hdr:
        rh_date = _detect_column(ret_hdr, ['RETURNDATE', 'returndate'])
        rh_amt = _detect_column(ret_hdr, ['RETURNAMOUNT', 'returnamount'])
        rh_loc = _detect_column(ret_hdr, ['LOCATIONCODE', 'LOCATION_CODE'])
        rh_sup = _detect_column(ret_hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE'])
        if rh_date and rh_amt:
            rw = [
                f"TRUNC(h.{rh_date}) >= TO_DATE(:df, 'YYYY-MM-DD')",
                f"TRUNC(h.{rh_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')",
            ]
            rp: Dict[str, Any] = {'df': d_from, 'dt': d_to}
            if loc and rh_loc:
                rw.append(f'h.{rh_loc} = :loc')
                rp['loc'] = int(loc)
            if filters.get('supplier_code') and rh_sup:
                rw.append(f'h.{rh_sup} = :sup')
                rp['sup'] = int(filters['supplier_code']) if str(filters['supplier_code']).isdigit() else filters['supplier_code']
            ret_amt = _f(_get_scalar(
                f'SELECT NVL(SUM(h.{rh_amt}), 0) FROM {ret_hdr} h WHERE {" AND ".join(rw)}',
                rp,
            ))
            ret_cnt = int(_get_scalar(f'SELECT COUNT(*) FROM {ret_hdr} h WHERE {" AND ".join(rw)}', rp) or 0)

    return {
        'total_purchases': total,
        'purchase_count': cnt,
        'purchase_return': ret_amt,
        'return_count': ret_cnt,
        'net_purchases': total - ret_amt,
        'purchase_source': purchase_source,
    }


def _detect_itemjournal_table() -> str:
    return _detect_table(['ITEMJOURNEL', 'itemjournel', 'ITEMJOURNAL', 'itemjournal']) or ''


def _journal_line_value_expr(j_alias: str = 'j') -> str:
    jn = _detect_itemjournal_table()
    if not jn:
        return '0'
    cols = {str(c).upper() for c in (_get_table_columns(jn) or [])}
    if 'AMOUNT' in cols:
        if 'QTY' in cols and 'RATE' in cols:
            return f'NVL({j_alias}.AMOUNT, NVL({j_alias}.QTY, 0) * NVL({j_alias}.RATE, 0))'
        return f'NVL({j_alias}.AMOUNT, 0)'
    if 'QTY' in cols and 'RATE' in cols:
        return f'NVL({j_alias}.QTY, 0) * NVL({j_alias}.RATE, 0)'
    return '0'


def _journal_date_filter(j_alias: str, d_from: str, d_to: str, params: Dict[str, Any]) -> str:
    jn = _detect_itemjournal_table()
    j_date = _detect_column(jn, ['CREATEDDATE', 'JOURNALDATE', 'TRANSDATE']) if jn else None
    if not j_date:
        return '1=0'
    params['j_df'] = d_from
    params['j_dt'] = d_to
    return (
        f"TRUNC({j_alias}.{j_date}) >= TO_DATE(:j_df, 'YYYY-MM-DD') "
        f"AND TRUNC({j_alias}.{j_date}) <= TO_DATE(:j_dt, 'YYYY-MM-DD')"
    )


def _journal_loc_filter(j_alias: str, loc: Optional[int], params: Dict[str, Any]) -> str:
    if loc is None:
        return ''
    jn = _detect_itemjournal_table()
    j_loc = _detect_column(jn, ['LOCATIONCODE', 'LOCATION_CODE']) if jn else None
    if not j_loc:
        return ''
    params['j_loc'] = int(loc)
    return f' AND {j_alias}.{j_loc} = :j_loc '


def _grn_metrics(filters: Dict[str, Any]) -> Tuple[float, int, float, int]:
    """GRN value from RECEIPTHDR/RECEIPTDTL; goods issue from ITEMJOURNAL outbound qty."""
    grn_amt, grn_cnt = _grn_receipt_totals(filters)
    _, issue_amt, issue_cnt = _goods_issue_metrics(filters)
    return grn_amt, grn_cnt, issue_amt, issue_cnt


def _goods_issue_metrics(filters: Dict[str, Any]) -> Tuple[float, float, int]:
    """Outbound stock value/qty from ITEMJOURNAL (sales, POS, transfers out)."""
    jn = _detect_itemjournal_table()
    if not jn:
        return 0.0, 0.0, 0
    loc = filters.get('branch')
    params: Dict[str, Any] = {}
    date_f = _journal_date_filter('j', filters['date_from'], filters['date_to'], params)
    loc_f = _journal_loc_filter('j', loc, params)
    line_val = _journal_line_value_expr('j')
    qty_col = _detect_column(jn, ['QTY', 'QUANTITY', 'quantity'])
    qty_expr = f'NVL(j.{qty_col}, 0)' if qty_col else '0'
    sd_col = _detect_column(jn, ['SOURCE_DOC', 'SOURCEDOC', 'source_doc'])
    tt_col = _detect_column(jn, ['TRANSTYPE', 'TRANSACTIONTYPE', 'transtype'])
    issue_types = (
        "UPPER(NVL(j.{c}, '')) IN ('BILL', 'POS', 'STKADJ', 'STOCK_ADJ', 'TRANSFER', 'ISSUE')"
    )
    type_filter = ''
    if sd_col:
        type_filter = f" AND ({issue_types.format(c=sd_col)} OR {qty_expr} < 0)"
    elif tt_col:
        type_filter = (
            f" AND (UPPER(NVL(j.{tt_col}, '')) IN "
            f"('SALES', 'BILL', 'POS', 'STOCK_ADJ', 'TRANSFER', 'ISSUE') OR {qty_expr} < 0)"
        )
    else:
        type_filter = f' AND {qty_expr} < 0'

    issue_amt = _f(_get_scalar(
        f"""SELECT NVL(SUM(ABS({line_val})), 0) FROM {jn} j
            WHERE {date_f} {loc_f} {type_filter} AND {qty_expr} < 0""",
        params,
    ))
    issue_qty = _f(_get_scalar(
        f"""SELECT NVL(SUM(ABS({qty_expr})), 0) FROM {jn} j
            WHERE {date_f} {loc_f} {type_filter} AND {qty_expr} < 0""",
        params,
    ))
    rc_col = _detect_column(jn, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    sn_col = _detect_column(jn, ['SLNO', 'slno'])
    if rc_col and sn_col:
        issue_cnt = int(_get_scalar(
            f"""SELECT COUNT(*) FROM (
                    SELECT DISTINCT j.{rc_col}, j.{sn_col}
                    FROM {jn} j
                    WHERE {date_f} {loc_f} {type_filter} AND {qty_expr} < 0
                )""",
            params,
        ) or 0)
    elif rc_col:
        issue_cnt = int(_get_scalar(
            f"""SELECT COUNT(DISTINCT j.{rc_col}) FROM {jn} j
                WHERE {date_f} {loc_f} {type_filter} AND {qty_expr} < 0""",
            params,
        ) or 0)
    else:
        issue_cnt = int(_get_scalar(
            f'SELECT COUNT(*) FROM {jn} j WHERE {date_f} {loc_f} {type_filter} AND {qty_expr} < 0',
            params,
        ) or 0)
    return issue_qty, issue_amt, issue_cnt


def _stock_adjustment_metrics(filters: Dict[str, Any]) -> Tuple[float, int]:
    d_from = filters['date_from']
    d_to = filters['date_to']
    loc = filters.get('branch')
    jn = _detect_itemjournal_table()
    if not jn:
        return 0.0, 0
    params: Dict[str, Any] = {}
    date_f = _journal_date_filter('j', d_from, d_to, params)
    loc_f = _journal_loc_filter('j', loc, params)
    line_val = _journal_line_value_expr('j')
    sd_col = _detect_column(jn, ['SOURCE_DOC', 'SOURCEDOC', 'source_doc'])
    tt_col = _detect_column(jn, ['TRANSTYPE', 'TRANSACTIONTYPE', 'transtype'])
    adj_filter = ''
    if sd_col:
        adj_filter = f" AND UPPER(NVL(j.{sd_col}, '')) IN ('STKADJ', 'STOCK_ADJ', 'STOCK ADJ', 'ADJUST')"
    elif tt_col:
        adj_filter = f" AND UPPER(NVL(j.{tt_col}, '')) IN ('STKADJ', 'STOCK_ADJ', 'STOCK ADJ', 'ADJUST', 'ADJUSTMENT')"
    # Opening-stock imports share SOURCE_DOC=STKADJ but are reported separately as
    # Opening Stock, so keep them out of the Stock Adjustment figure to avoid overlap.
    if tt_col:
        adj_filter += f" AND UPPER(NVL(j.{tt_col}, '')) NOT IN ('OPENING_STOCK', 'OPENING STOCK', 'OPENING')"
    amt = _f(_get_scalar(
        f'SELECT NVL(SUM(ABS({line_val})), 0) FROM {jn} j WHERE {date_f} {loc_f} {adj_filter}',
        params,
    ))
    cnt = int(_get_scalar(
        f'SELECT COUNT(*) FROM {jn} j WHERE {date_f} {loc_f} {adj_filter}',
        params,
    ) or 0)
    return amt, cnt


def _stock_position_metrics(filters: Dict[str, Any]) -> Dict[str, float]:
    """Opening/closing inventory value from ITEMJOURNAL cumulative movement (branch-scoped)."""
    jn = _detect_itemjournal_table()
    d_from = filters['date_from']
    d_to = filters['date_to']
    loc = filters.get('branch')
    if not jn:
        return {'opening_stock': 0.0, 'closing_stock': 0.0, 'opening_qty': 0.0, 'closing_qty': 0.0}
    j_date = _detect_column(jn, ['CREATEDDATE', 'JOURNALDATE', 'TRANSDATE'])
    j_loc = _detect_column(jn, ['LOCATIONCODE', 'LOCATION_CODE'])
    qty_col = _detect_column(jn, ['QTY', 'QUANTITY', 'quantity'])
    if not j_date or not qty_col:
        return {'opening_stock': 0.0, 'closing_stock': 0.0, 'opening_qty': 0.0, 'closing_qty': 0.0}
    line_val = _journal_line_value_expr('j')
    tt_col = _detect_column(jn, ['TRANSTYPE', 'TRANSACTIONTYPE', 'transtype'])
    params: Dict[str, Any] = {'sp_df': d_from, 'sp_dt': d_to}
    loc_sql = ''
    if loc and j_loc:
        loc_sql = f' AND j.{j_loc} = :sp_loc '
        params['sp_loc'] = int(loc)

    # Opening stock is sourced from the dedicated OPENING_STOCK journal entries
    # (opening-balance imports) dated on/before the report period end, branch-scoped.
    opening_from_tt: Optional[float] = None
    opening_qty_from_tt: float = 0.0
    if tt_col:
        opening_row = _safe_rows(
            f"""SELECT NVL(SUM({line_val}), 0) AS opening_value,
                       NVL(SUM(NVL(j.{qty_col}, 0)), 0) AS opening_qty
                FROM {jn} j
                WHERE UPPER(NVL(j.{tt_col}, '')) IN ('OPENING_STOCK', 'OPENING STOCK', 'OPENING')
                  AND TRUNC(j.{j_date}) <= TO_DATE(:sp_dt, 'YYYY-MM-DD')
                  {loc_sql}""",
            params,
        )
        orow = (opening_row or [{}])[0]
        val = _f(orow.get('opening_value'))
        cnt_check = orow.get('opening_value')
        if cnt_check is not None and abs(val) > 1e-09:
            opening_from_tt = val
            opening_qty_from_tt = _f(orow.get('opening_qty'))

    row = _safe_rows(
        f"""SELECT
                NVL(SUM(CASE WHEN TRUNC(j.{j_date}) < TO_DATE(:sp_df, 'YYYY-MM-DD')
                             THEN {line_val} ELSE 0 END), 0) AS opening_value,
                NVL(SUM(CASE WHEN TRUNC(j.{j_date}) <= TO_DATE(:sp_dt, 'YYYY-MM-DD')
                             THEN {line_val} ELSE 0 END), 0) AS closing_value,
                NVL(SUM(CASE WHEN TRUNC(j.{j_date}) < TO_DATE(:sp_df, 'YYYY-MM-DD')
                             THEN NVL(j.{qty_col}, 0) ELSE 0 END), 0) AS opening_qty,
                NVL(SUM(CASE WHEN TRUNC(j.{j_date}) <= TO_DATE(:sp_dt, 'YYYY-MM-DD')
                             THEN NVL(j.{qty_col}, 0) ELSE 0 END), 0) AS closing_qty
            FROM {jn} j
            WHERE 1=1 {loc_sql}""",
        params,
    )
    r = (row or [{}])[0]
    if opening_from_tt is not None:
        opening_value = opening_from_tt
        opening_qty = opening_qty_from_tt
    else:
        opening_value = _f(r.get('opening_value'))
        opening_qty = _f(r.get('opening_qty'))
    return {
        'opening_stock': round(opening_value, 2),
        'closing_stock': round(_f(r.get('closing_value')), 2),
        'opening_qty': round(opening_qty, 3),
        'closing_qty': round(_f(r.get('closing_qty')), 3),
    }


def _inventory_snapshot(loc: Optional[int]) -> Dict[str, Any]:
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return {}
    stk_col = _detect_column(im, ['CURRENTSTOCK', 'currentstock', 'STOCK'])
    cost_col = _detect_column(im, ['AVERAGECOST', 'averagecost', 'COSTPRICE', 'costprice'])
    active_col = _detect_column(im, ['ACTIVE', 'active', 'ISACTIVE'])
    loc_col = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE'])
    ic_col = _detect_column(im, ['ITEMCODE', 'ITEM_CODE'])
    name_col = _detect_column(im, ['ITEMNAME', 'ITEM_NAME'])
    min_col = _detect_column(im, ['MINIMUMSTOCK', 'MINIMUM_STOCK', 'reorderlevel'])
    where = '1=1'
    params: Dict[str, Any] = {}
    if loc and loc_col:
        where += f' AND im.{loc_col} = :loc'
        params['loc'] = int(loc)
    if active_col:
        where += f" AND NVL(im.{active_col}, 'Y') IN ('Y', '1', 'T')"
    stk_expr = f'NVL(im.{stk_col}, 0)' if stk_col else '0'
    cost_expr = f'NVL(im.{cost_col}, 0)' if cost_col else '0'
    q_base = f'FROM {im} im WHERE {where}'
    total_items = int(_get_scalar(f'SELECT COUNT(*) {q_base}', params) or 0)
    inv_value = _f(_get_scalar(f'SELECT NVL(SUM({stk_expr} * {cost_expr}), 0) {q_base}', params))
    stock_qty = _f(_get_scalar(f'SELECT NVL(SUM({stk_expr}), 0) {q_base}', params))
    out_of_stock = int(_get_scalar(f'SELECT COUNT(*) {q_base} AND {stk_expr} <= 0', params) or 0)
    negative = int(_get_scalar(f'SELECT COUNT(*) {q_base} AND {stk_expr} < 0', params) or 0)
    low_stock = 0
    if min_col and stk_col:
        low_stock = int(_get_scalar(
            f'SELECT COUNT(*) {q_base} AND {stk_expr} > 0 AND {stk_expr} <= NVL(im.{min_col}, 0)',
            params,
        ) or 0)
    dead_stock = int(_get_scalar(f'SELECT COUNT(*) {q_base} AND {stk_expr} > 0', params) or 0) - low_stock
    highest = []
    if ic_col and name_col and stk_col and cost_col:
        highest = _safe_rows(
            _sql_top_n(
                f"""SELECT im.{ic_col} AS item_code, im.{name_col} AS item_name,
                           {stk_expr} AS qty, ({stk_expr} * {cost_expr}) AS stock_value
                    {q_base} AND {stk_expr} > 0
                    ORDER BY ({stk_expr} * {cost_expr}) DESC""",
                5,
            ),
            params,
        )
    return {
        'total_items': total_items,
        'active_items': total_items,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'negative_stock': negative,
        'dead_stock': max(dead_stock, 0),
        'inventory_value': inv_value,
        'current_stock_qty': stock_qty,
        'highest_value_stock': highest,
    }


def _inventory_snapshot_light(loc: Optional[int]) -> Dict[str, Any]:
    """Two-query inventory totals for mobile (skips stock health / top-item scans)."""
    im = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im:
        return {}
    stk_col = _detect_column(im, ['CURRENTSTOCK', 'currentstock', 'STOCK'])
    cost_col = _detect_column(im, ['AVERAGECOST', 'averagecost', 'COSTPRICE', 'costprice'])
    active_col = _detect_column(im, ['ACTIVE', 'active', 'ISACTIVE'])
    loc_col = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE'])
    where = '1=1'
    params: Dict[str, Any] = {}
    if loc and loc_col:
        where += f' AND im.{loc_col} = :loc'
        params['loc'] = int(loc)
    if active_col:
        where += f" AND NVL(im.{active_col}, 'Y') IN ('Y', '1', 'T')"
    stk_expr = f'NVL(im.{stk_col}, 0)' if stk_col else '0'
    cost_expr = f'NVL(im.{cost_col}, 0)' if cost_col else '0'
    q_base = f'FROM {im} im WHERE {where}'
    inv_value = _f(_get_scalar(f'SELECT NVL(SUM({stk_expr} * {cost_expr}), 0) {q_base}', params))
    stock_qty = _f(_get_scalar(f'SELECT NVL(SUM({stk_expr}), 0) {q_base}', params))
    return {
        'inventory_value': inv_value,
        'current_stock_qty': stock_qty,
    }


def _outstanding_totals() -> Tuple[float, float]:
    ar = 0.0
    ap = 0.0
    try:
        for row in get_accounts_receivable_summary() or []:
            ar += _f(row.get('balance') or row.get('outstanding') or row.get('amount'))
    except Exception:
        pass
    try:
        for row in get_accounts_payable_summary() or []:
            ap += _f(row.get('balance') or row.get('outstanding') or row.get('amount'))
    except Exception:
        pass
    return ar, ap


def _gl_source_cash_total(source: str, d_from: str, d_to: str) -> Tuple[float, int]:
    """Sum net cash from GL vouchers (AR_RECEIPT customer collections, AP_RECEIPT supplier payments)."""
    try:
        ensure_gl_tables()
    except Exception:
        return 0.0, 0
    src = (source or '').strip().upper()
    if src not in ('AR_RECEIPT', 'AP_RECEIPT'):
        return 0.0, 0
    params: Dict[str, Any] = {'src': src, 'df': d_from, 'dt': d_to}
    if src == 'AR_RECEIPT':
        cash_expr = (
            "SUM(CASE WHEN UPPER(NVL(d.PARTY_TYPE, '')) <> 'CUSTOMER' "
            'AND NVL(d.DEBIT, 0) > 0 THEN NVL(d.DEBIT, 0) ELSE 0 END)'
        )
    else:
        cash_expr = (
            "SUM(CASE WHEN UPPER(NVL(d.PARTY_TYPE, '')) <> 'SUPPLIER' "
            'AND NVL(d.CREDIT, 0) > 0 THEN NVL(d.CREDIT, 0) ELSE 0 END)'
        )
    try:
        amt = _f(_get_scalar(
            f"""SELECT NVL(SUM(v.cash_amt), 0) FROM (
                    SELECT h.VOUCHER_NO, {cash_expr} AS cash_amt
                    FROM {GL_HDR_TABLE} h
                    JOIN {GL_DTL_TABLE} d ON d.VOUCHER_NO = h.VOUCHER_NO
                    WHERE UPPER(NVL(h.SOURCE, '')) = :src
                      AND TRUNC(h.VOUCHER_DATE) >= TO_DATE(:df, 'YYYY-MM-DD')
                      AND TRUNC(h.VOUCHER_DATE) <= TO_DATE(:dt, 'YYYY-MM-DD')
                    GROUP BY h.VOUCHER_NO
                ) v""",
            params,
        ))
        cnt = int(_get_scalar(
            f"""SELECT COUNT(DISTINCT h.VOUCHER_NO)
                FROM {GL_HDR_TABLE} h
                WHERE UPPER(NVL(h.SOURCE, '')) = :src
                  AND TRUNC(h.VOUCHER_DATE) >= TO_DATE(:df, 'YYYY-MM-DD')
                  AND TRUNC(h.VOUCHER_DATE) <= TO_DATE(:dt, 'YYYY-MM-DD')""",
            params,
        ) or 0)
        return amt, cnt
    except Exception:
        return 0.0, 0


def _customer_receipts_total(filters: Dict[str, Any]) -> float:
    d_from = filters['date_from']
    d_to = filters['date_to']
    gl_amt, _ = _gl_source_cash_total('AR_RECEIPT', d_from, d_to)
    if gl_amt > 0:
        return gl_amt
    ts = _detect_table(['tbltempsettlement', 'TBLTEMPSETTLEMENT'])
    if ts:
        paid_col = _detect_column(ts, ['PAIDAMOUNT', 'paidamount', 'AMOUNT'])
        date_col = _detect_column(ts, ['PAIDDATE', 'paiddate', 'SETTLEMENTDATE'])
        flag_col = _detect_column(ts, ['FLAG', 'flag'])
        if paid_col and date_col:
            flag_f = f" AND NVL({flag_col}, 'R') = 'R' " if flag_col else ''
            return _f(_get_scalar(
                f"""SELECT NVL(SUM({paid_col}), 0) FROM {ts}
                    WHERE TRUNC({date_col}) >= TO_DATE(:df, 'YYYY-MM-DD')
                      AND TRUNC({date_col}) <= TO_DATE(:dt, 'YYYY-MM-DD')
                      {flag_f}""",
                {'df': d_from, 'dt': d_to},
            ))
    settle = _detect_table(['tblsettlement', 'TBLSETTLEMENT'])
    if settle:
        paid_col = _detect_column(settle, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
        date_col = _detect_column(settle, ['PAIDDATE', 'paiddate', 'SETTLEMENTDATE'])
        if paid_col and date_col:
            return _f(_get_scalar(
                f"""SELECT NVL(SUM({paid_col}), 0) FROM {settle}
                    WHERE TRUNC({date_col}) >= TO_DATE(:df, 'YYYY-MM-DD')
                      AND TRUNC({date_col}) <= TO_DATE(:dt, 'YYYY-MM-DD')""",
                {'df': d_from, 'dt': d_to},
            ))
    return 0.0


def _supplier_payments_total(filters: Dict[str, Any]) -> float:
    d_from = filters['date_from']
    d_to = filters['date_to']
    gl_amt, _ = _gl_source_cash_total('AP_RECEIPT', d_from, d_to)
    if gl_amt > 0:
        return gl_amt
    ts = _detect_table(['PAYMENTVOUCHER', 'paymentvoucher', 'TBLPAYMENT'])
    if not ts:
        return 0.0
    amt_col = _detect_column(ts, ['AMOUNT', 'PAYMENTAMOUNT', 'NETAMOUNT', 'amount'])
    date_col = _detect_column(ts, ['PAYMENTDATE', 'VOUCHERDATE', 'TRANSDATE', 'paymentdate'])
    sup_col = _detect_column(ts, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    if not amt_col or not date_col:
        return 0.0
    where = [
        f'TRUNC({date_col}) >= TO_DATE(:df, \'YYYY-MM-DD\')',
        f'TRUNC({date_col}) <= TO_DATE(:dt, \'YYYY-MM-DD\')',
    ]
    params: Dict[str, Any] = {'df': d_from, 'dt': d_to}
    if filters.get('supplier_code') and sup_col:
        sup = filters['supplier_code']
        where.append(f'{sup_col} = :sup')
        params['sup'] = int(sup) if str(sup).isdigit() else sup
    return _f(_get_scalar(
        f'SELECT NVL(SUM({amt_col}), 0) FROM {ts} WHERE {" AND ".join(where)}',
        params,
    ))


def _collections_payments(filters: Dict[str, Any]) -> Tuple[float, float]:
    receipts = _customer_receipts_total(filters)
    try:
        pl = get_profit_and_loss_report(filters['date_from'], filters['date_to'])
    except Exception:
        pl = {}
    expenses = _f((pl or {}).get('total_expense') or (pl or {}).get('total_expenses') or (pl or {}).get('expenses'))
    return receipts, expenses


def _tender_category_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {
        'CASH': 'Cash',
        'CARD': 'Card',
        'VISA': 'Card',
        'MC': 'Card',
        'MASTERCARD': 'Card',
        'CREDIT': 'Credit',
        'WALLET': 'Online',
        'ONLINE': 'Online',
        'LOYALTY': 'Online',
        'POINTS': 'Online',
        'VOUCHER': 'Online',
    }
    try:
        for tr in list_pos_tender_types(active_only=False) or []:
            code = str(tr.get('tender_code') or '').strip().upper()
            if not code:
                continue
            cat = str(tr.get('category') or '').strip()
            if cat.lower() == 'cash':
                mapping[code] = 'Cash'
            elif cat.lower() == 'card':
                mapping[code] = 'Card'
            elif cat.lower() == 'credit':
                mapping[code] = 'Credit'
            elif cat.lower() in ('wallet', 'voucher', 'online'):
                mapping[code] = 'Online'
            elif code not in mapping:
                mapping[code] = cat or 'Cash'
    except Exception:
        pass
    return mapping


def _fetch_sales_bill_rows_for_paymodes(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    ctx = _get_sales_ctx()
    if not ctx.get('valid'):
        return []
    d_from = _parse_date(filters['date_from'], date.today())
    d_to = _parse_date(filters['date_to'], date.today())
    loc = filters.get('branch')
    amt_expr = _sales_amt_expr(ctx)
    where, params = _billhdr_filters(ctx, d_from, d_to, loc, f' AND {amt_expr} >= 0 ')
    cols = {str(c).upper() for c in (_get_table_columns(ctx['hdr']) or [])}
    select_cols = ['bh.' + ctx['no_col'], 'bh.' + ctx['amt_col']]
    for optional in (
        'BILLTYPE', 'CUSTOMERCODE', 'CASHAMOUNT', 'CARDAMOUNT', 'WALLETAMOUNT',
        'ONLINEAMOUNT', 'CREDITAMOUNT', 'DISCOUNTAMOUNT', 'TAXAMOUNT', 'VATAMOUNT',
        'PAYMENTMODE', 'PAYMODE', 'PAYTYPE',
    ):
        detected = _detect_column(ctx['hdr'], [optional, optional.lower()])
        if detected and detected.upper() in cols:
            select_cols.append(f'bh.{detected}')
    return _safe_rows(
        f"SELECT {', '.join(select_cols)} FROM {ctx['hdr']} bh WHERE 1=1 {where}",
        params,
    ) or []


def _payment_distribution(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    loc = int(filters.get('branch') or 1)
    bill_rows = _fetch_sales_bill_rows_for_paymodes(filters)
    bill_nos: List[int] = []
    for r in bill_rows:
        for key in ('billno', 'BILLNO'):
            if r.get(key) is not None:
                try:
                    bn = int(r.get(key))
                    if bn > 0:
                        bill_nos.append(bn)
                except (TypeError, ValueError):
                    pass
                break
    paymode_totals = _merge_pos_shift_tender_totals(loc, bill_rows, bill_nos) if bill_rows else {}
    if not paymode_totals:
        sales = _sales_metrics(filters)
        paymode_totals = {
            'CASH': sales['cash_sales'],
            'CREDIT': sales['credit_sales'],
        }

    cat_map = _tender_category_map()
    buckets: Dict[str, float] = {'Cash': 0.0, 'Card': 0.0, 'Credit': 0.0, 'Online': 0.0}
    for code, amt in (paymode_totals or {}).items():
        ku = str(code or '').strip().upper()
        try:
            val = float(amt or 0)
        except (TypeError, ValueError):
            val = 0.0
        if abs(val) <= 0.0005:
            continue
        label = cat_map.get(ku, 'Cash')
        if label not in buckets:
            if 'card' in label.lower():
                label = 'Card'
            elif 'credit' in label.lower():
                label = 'Credit'
            elif label.lower() in ('wallet', 'online', 'voucher'):
                label = 'Online'
            else:
                label = 'Cash'
        buckets[label] = round(buckets.get(label, 0.0) + val, 2)

    total = sum(buckets.values()) or 1.0
    out: List[Dict[str, Any]] = []
    for label in ('Cash', 'Card', 'Credit', 'Online'):
        amt = round(buckets.get(label, 0.0), 2)
        if amt <= 0:
            continue
        out.append({
            'label': label,
            'amount': amt,
            'pct': round(amt / total * 100, 1),
        })
    if not out:
        sales = _sales_metrics(filters)
        total_sales = sales['total_sales'] or 1.0
        out = [
            {'label': 'Cash', 'amount': round(sales['cash_sales'], 2),
             'pct': round(sales['cash_sales'] / total_sales * 100, 1)},
            {'label': 'Credit', 'amount': round(sales['credit_sales'], 2),
             'pct': round(sales['credit_sales'] / total_sales * 100, 1)},
        ]
    return out


def _daily_trend(filters: Dict[str, Any], field: str) -> List[Dict[str, Any]]:
    d_from = _parse_date(filters['date_from'], date.today())
    d_to = _parse_date(filters['date_to'], date.today())
    loc = filters.get('branch')
    if field == 'sales':
        ctx = _get_sales_ctx()
        if not ctx.get('valid'):
            return []
        amt_expr = _sales_amt_expr(ctx)
        where, params = _billhdr_filters(ctx, d_from, d_to, loc, f' AND {amt_expr} >= 0 ')
        rows = _safe_rows(
            f"""SELECT TRUNC(bh.{ctx['date_col']}) AS dt, NVL(SUM({amt_expr}), 0) AS amt
                FROM {ctx['hdr']} bh WHERE 1=1 {where}
                GROUP BY TRUNC(bh.{ctx['date_col']}) ORDER BY 1""",
            params,
        )
    elif field == 'purchase':
        rows: List[Dict[str, Any]] = []
        hdr = _detect_table(['LPOHDR', 'lpohdr'])
        h_date = _detect_column(hdr or '', ['LPODATE', 'LPO_DATE']) if hdr else None
        h_amt = _detect_column(hdr or '', ['LPOAMOUNT', 'LPO_AMOUNT', 'NETAMOUNT']) if hdr else None
        h_loc = _detect_column(hdr or '', ['LOCATIONCODE', 'LOCATION_CODE']) if hdr else None
        h_del = _detect_column(hdr or '', ['DELFLAG', 'DEL_FLAG']) if hdr else None
        if hdr and h_date:
            where = (
                f'TRUNC(h.{h_date}) >= TRUNC(:d_from) AND TRUNC(h.{h_date}) <= TRUNC(:d_to)'
            )
            params: Dict[str, Any] = {'d_from': d_from, 'd_to': d_to}
            if loc and h_loc:
                where += f' AND h.{h_loc} = :loc'
                params['loc'] = int(loc)
            if h_del:
                where += f" AND NVL(h.{h_del}, 'N') = 'N'"
            rows = _safe_rows(
                f"""SELECT TRUNC(h.{h_date}) AS dt, NVL(SUM(h.{h_amt or h_date}), 0) AS amt
                    FROM {hdr} h WHERE {where} GROUP BY TRUNC(h.{h_date}) ORDER BY 1""",
                params,
            ) or []
        if not rows:
            return _grn_receipt_daily_trend(filters)
    else:
        return []
    out = []
    for r in rows:
        dt = r.get('dt')
        out.append({
            'date': dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10],
            'amount': round(_f(r.get('amt')), 2),
        })
    return out


def _supplier_join_and_name(hdr_sup: str, hdr_loc: Optional[str] = None) -> Tuple[str, str]:
    sup_tbl = _detect_table(['SUPPLIER', 'supplier', 'SUPPLIERS'])
    if not sup_tbl:
        return '', f'MAX(h.{hdr_sup})'
    s_code = _detect_column(sup_tbl, ['SUPPLIERCODE', 'SUPPLIER_CODE']) or 'SUPPLIERCODE'
    s_name = _detect_column(sup_tbl, ['SUPPLIERNAME', 'SUPPLIER_NAME']) or s_code
    s_loc = _detect_column(sup_tbl, ['LOCATIONCODE', 'LOCATION_CODE'])
    join = f' LEFT JOIN {sup_tbl} s ON s.{s_code} = h.{hdr_sup} '
    if hdr_loc and s_loc:
        join += f' AND s.{s_loc} = h.{hdr_loc} '
    return join, f'NVL(MAX(s.{s_name}), MAX(h.{hdr_sup}))'


def _top_suppliers_from_grn(filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """Top suppliers by goods received (GRN) — used when LPO has no rows in the period."""
    d_from = filters['date_from']
    d_to = filters['date_to']
    loc = filters.get('branch')
    rh = _detect_table(['RECEIPTHDR', 'receipthdr'])
    rd = _detect_table(['RECEIPTDTL', 'receiptdtl'])
    if not rh:
        return []
    r_date = _detect_column(rh, ['RECEIPTDATE', 'RECEIPT_DATE', 'receiptdate'])
    r_loc = _detect_column(rh, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    r_del = _detect_column(rh, ['DELFLAG', 'DEL_FLAG', 'delflag'])
    r_reset = _detect_column(rh, ['RESETNO', 'RESET_NO', 'resetno'])
    r_no = _detect_column(rh, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
    r_sup = _detect_column(rh, ['SUPPLIERCODE', 'SUPPLIER_CODE', 'suppliercode'])
    r_inv_amt = _detect_column(rh, ['INVOICEAMOUNT', 'INVOICE_AMOUNT', 'invoiceamount'])
    r_hdr_amt = _detect_column(rh, ['RECEIPTAMOUNT', 'receiptamount', 'NETAMOUNT', 'GRNAMOUNT'])
    if not r_date or not r_sup:
        return []
    where = [
        f"TRUNC(h.{r_date}) >= TO_DATE(:df, 'YYYY-MM-DD')",
        f"TRUNC(h.{r_date}) <= TO_DATE(:dt, 'YYYY-MM-DD')",
        f'h.{r_sup} IS NOT NULL',
    ]
    params: Dict[str, Any] = {'df': d_from, 'dt': d_to}
    if loc and r_loc:
        where.append(f'h.{r_loc} = :loc')
        params['loc'] = int(loc)
    if r_del:
        where.append(f"NVL(h.{r_del}, 'N') = 'N'")
    if r_reset:
        where.append(f'h.{r_reset} = :rn')
        params['rn'] = _GRN_RESET_NO
    if filters.get('supplier_code'):
        sup = filters['supplier_code']
        where.append(f'h.{r_sup} = :sup')
        params['sup'] = int(sup) if str(sup).isdigit() else sup
    w = ' AND '.join(where)
    sup_join, sup_name = _supplier_join_and_name(r_sup, r_loc)

    if rd and r_no:
        d_loc = _detect_column(rd, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        d_no = _detect_column(rd, ['RECEIPTNO', 'RECEIPT_NO', 'receiptno'])
        d_reset = _detect_column(rd, ['RESETNO', 'RESET_NO', 'resetno'])
        d_qty = _detect_column(rd, ['QUANTITY', 'QTY', 'quantity', 'RECEIPTQTY'])
        d_rate = _detect_column(rd, ['RATE', 'rate', 'COSTPRICE'])
        d_disc = _detect_column(rd, ['DISCOUNT', 'discount', 'ITDISC', 'LINEDISCOUNT'])
        d_amt = _detect_column(rd, ['AMOUNT', 'LINEAMOUNT', 'lineamount', 'NETAMOUNT'])
        join_parts = [f'd.{d_no} = h.{r_no}']
        if d_loc and r_loc:
            join_parts.append(f'd.{d_loc} = h.{r_loc}')
        if d_reset and r_reset:
            join_parts.append(f'd.{d_reset} = h.{r_reset}')
        if d_amt:
            line_amt = f'ABS(NVL(d.{d_amt}, 0))'
        elif d_qty and d_rate:
            disc_expr = f' - NVL(d.{d_disc}, 0)' if d_disc else ''
            line_amt = f'ABS(GREATEST(NVL(d.{d_qty}, 0) * NVL(d.{d_rate}, 0){disc_expr}, 0))'
        else:
            line_amt = '0'
        q = f"""SELECT h.{r_sup} AS code, {sup_name} AS name,
                       NVL(SUM({line_amt}), 0) AS amount
                FROM {rh} h
                JOIN {rd} d ON {' AND '.join(join_parts)}
                {sup_join}
                WHERE {w}
                GROUP BY h.{r_sup}
                HAVING NVL(SUM({line_amt}), 0) <> 0
                ORDER BY 3 DESC"""
    else:
        amt_col = r_inv_amt or r_hdr_amt
        if not amt_col:
            return []
        q = f"""SELECT h.{r_sup} AS code, {sup_name} AS name,
                       NVL(SUM(h.{amt_col}), 0) AS amount
                FROM {rh} h
                {sup_join}
                WHERE {w}
                GROUP BY h.{r_sup}
                HAVING NVL(SUM(h.{amt_col}), 0) <> 0
                ORDER BY 3 DESC"""
    rows = _safe_rows(_sql_top_n(q, limit), params)
    return [{'code': r.get('code'), 'name': r.get('name') or '', 'amount': round(_f(r.get('amount')), 2)} for r in rows]


def _top_suppliers_from_lpo(filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    d_from = _parse_date(filters['date_from'], date.today())
    d_to = _parse_date(filters['date_to'], date.today())
    loc = filters.get('branch')
    hdr = _detect_table(['LPOHDR', 'lpohdr'])
    if not hdr:
        return []
    h_date = _detect_column(hdr, ['LPODATE', 'LPO_DATE'])
    h_sup = _detect_column(hdr, ['SUPPLIERCODE', 'SUPPLIER_CODE'])
    h_amt = _detect_column(hdr, ['LPOAMOUNT', 'LPO_AMOUNT', 'NETAMOUNT', 'netamount'])
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'LOCATION_CODE'])
    h_del = _detect_column(hdr, ['DELFLAG', 'DEL_FLAG'])
    if not h_date or not h_sup or not h_amt:
        return []
    where = [
        f'TRUNC(h.{h_date}) >= TRUNC(:d_from)',
        f'TRUNC(h.{h_date}) <= TRUNC(:d_to)',
        f'h.{h_sup} IS NOT NULL',
    ]
    params: Dict[str, Any] = {'d_from': d_from, 'd_to': d_to}
    if loc and h_loc:
        where.append(f'h.{h_loc} = :loc')
        params['loc'] = int(loc)
    if h_del:
        where.append(f"NVL(h.{h_del}, 'N') = 'N'")
    if filters.get('supplier_code'):
        sup = filters['supplier_code']
        where.append(f'h.{h_sup} = :sup')
        params['sup'] = int(sup) if str(sup).isdigit() else sup
    w = ' AND '.join(where)
    sup_join, sup_name = _supplier_join_and_name(h_sup, h_loc)
    rows = _safe_rows(
        _sql_top_n(
            f"""SELECT h.{h_sup} AS code, {sup_name} AS name,
                       NVL(SUM(h.{h_amt}), 0) AS amount
                FROM {hdr} h
                {sup_join}
                WHERE {w}
                GROUP BY h.{h_sup}
                HAVING NVL(SUM(h.{h_amt}), 0) <> 0
                ORDER BY 3 DESC""",
            limit,
        ),
        params,
    )
    return [{'code': r.get('code'), 'name': r.get('name') or '', 'amount': round(_f(r.get('amount')), 2)} for r in rows]


def _top_suppliers(filters: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """Top suppliers by GRN receipts; falls back to LPO when no GRN in the period."""
    rows = _top_suppliers_from_grn(filters, limit)
    if rows:
        return rows
    return _top_suppliers_from_lpo(filters, limit)


def _im_lookup_join(
    master_tables: List[str],
    code_cols: List[str],
    name_cols: List[str],
    alias: str,
    im_col: str,
    *,
    flag: Optional[str] = 'C',
) -> Tuple[str, str]:
    """Join master table for descriptive name (category, brand, etc.)."""
    tbl = _detect_table(master_tables)
    if not tbl:
        return '', f'MAX(im.{im_col})'
    m_code = _detect_column(tbl, code_cols)
    m_name = _detect_column(tbl, name_cols)
    m_flag = _detect_column(tbl, ['FLAG', 'flag'])
    if not m_code or not m_name:
        return '', f'MAX(im.{im_col})'
    flag_sql = f" AND {alias}.{m_flag} = '{flag}' " if flag and m_flag else ''
    join = f' LEFT JOIN {tbl} {alias} ON {alias}.{m_code} = im.{im_col}{flag_sql} '
    name_expr = f'NVL(MAX({alias}.{m_name}), MAX(im.{im_col}))'
    return join, name_expr


def _top_entities(filters: Dict[str, Any], kind: str, limit: int = 10) -> List[Dict[str, Any]]:
    if kind == 'suppliers':
        return _top_suppliers(filters, limit)
    d_from = _parse_date(filters['date_from'], date.today())
    d_to = _parse_date(filters['date_to'], date.today())
    loc = filters.get('branch')
    ctx = _get_sales_ctx()
    if not ctx.get('valid'):
        return []
    amt_expr = _sales_amt_expr(ctx)
    line_amt = _sales_line_amt_expr(ctx)
    where, params = _billhdr_filters(ctx, d_from, d_to, loc, f' AND {amt_expr} >= 0 ')
    cust_tbl = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERS'])
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster'])
    cust_join = ''
    cust_name = f'MAX(bh.{ctx["cust_col"]})'
    if kind == 'customers' and cust_tbl and ctx.get('cust_col'):
        cc = _detect_column(cust_tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE'])
        cn = _detect_column(cust_tbl, ['CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME'])
        if cc:
            cust_join = f' LEFT JOIN {cust_tbl} c ON c.{cc} = bh.{ctx["cust_col"]} '
            cust_name = f'NVL(MAX(c.{cn or cc}), MAX(bh.{ctx["cust_col"]}))'
    if kind == 'customers':
        if not ctx.get('cust_col'):
            return []
        rows = _safe_rows(
            _sql_top_n(
                f"""SELECT bh.{ctx['cust_col']} AS code, {cust_name} AS name,
                           NVL(SUM({amt_expr}), 0) AS amount
                    FROM {ctx['hdr']} bh
                    {cust_join}
                    WHERE 1=1 {where}
                    GROUP BY bh.{ctx['cust_col']}
                    ORDER BY 3 DESC""",
                limit,
            ),
            params,
        )
    elif kind == 'items':
        if not ctx.get('dtl') or not ctx.get('d_bill') or not ctx.get('d_item'):
            return []
        cat_f = brand_f = ''
        if filters.get('category_code'):
            cat_f = ' AND im.CATEGORYCODE = :cat '
            params['cat'] = filters['category_code']
        if filters.get('brand_code'):
            brand_f = ' AND im.BRANDCODE = :brand '
            params['brand'] = filters['brand_code']
        im_join = f' LEFT JOIN {im_tbl} im ON im.ITEMCODE = bd.{ctx["d_item"]} ' if im_tbl else ''
        rows = _safe_rows(
            _sql_top_n(
                f"""SELECT bd.{ctx['d_item']} AS code,
                           NVL(MAX(im.ITEMNAME), MAX(bd.{ctx['d_item']})) AS name,
                           NVL(SUM({line_amt}), 0) AS amount
                    FROM {ctx['hdr']} bh
                    JOIN {ctx['dtl']} bd ON {_sales_hdr_dtl_join(ctx)}
                    {im_join}
                    WHERE 1=1 {where} {cat_f} {brand_f}
                    GROUP BY bd.{ctx['d_item']}
                    ORDER BY 3 DESC""",
                limit,
            ),
            params,
        )
    elif kind == 'categories':
        if not ctx.get('dtl') or not im_tbl:
            return []
        cat_code = _detect_column(im_tbl, ['CATEGORYCODE', 'CATEGORY_CODE']) or 'CATEGORYCODE'
        cat_join, cat_name_expr = _im_lookup_join(
            ['CATEGORY', 'category', 'categorymaster'],
            ['CODE', 'CATEGORYCODE', 'categorycode'],
            ['NAME', 'CATEGORYNAME', 'categoryname', 'CATNAME'],
            'cat',
            cat_code,
        )
        rows = _safe_rows(
            _sql_top_n(
                f"""SELECT im.{cat_code} AS code, {cat_name_expr} AS name,
                           NVL(SUM({line_amt}), 0) AS amount
                    FROM {ctx['hdr']} bh
                    JOIN {ctx['dtl']} bd ON {_sales_hdr_dtl_join(ctx)}
                    LEFT JOIN {im_tbl} im ON im.ITEMCODE = bd.{ctx['d_item']}
                    {cat_join}
                    WHERE 1=1 {where}
                    GROUP BY im.{cat_code}
                    ORDER BY 3 DESC""",
                limit,
            ),
            params,
        )
    elif kind == 'brands':
        if not ctx.get('dtl') or not im_tbl:
            return []
        brand_code = _detect_column(im_tbl, ['BRANDCODE', 'BRAND_CODE']) or 'BRANDCODE'
        brand_join, brand_name_expr = _im_lookup_join(
            ['BRAND', 'brand', 'brandmaster'],
            ['CODE', 'BRANDCODE', 'brandcode'],
            ['NAME', 'BRANDNAME', 'brandname'],
            'br',
            brand_code,
            flag=None,
        )
        rows = _safe_rows(
            _sql_top_n(
                f"""SELECT im.{brand_code} AS code, {brand_name_expr} AS name,
                           NVL(SUM({line_amt}), 0) AS amount
                    FROM {ctx['hdr']} bh
                    JOIN {ctx['dtl']} bd ON {_sales_hdr_dtl_join(ctx)}
                    LEFT JOIN {im_tbl} im ON im.ITEMCODE = bd.{ctx['d_item']}
                    {brand_join}
                    WHERE 1=1 {where}
                    GROUP BY im.{brand_code}
                    ORDER BY 3 DESC""",
                limit,
            ),
            params,
        )
    else:
        return []
    return [{'code': r.get('code'), 'name': r.get('name') or '', 'amount': round(_f(r.get('amount')), 2)} for r in rows]


def _kpi(id_: str, label: str, value: float, icon: str, fmt: str = 'currency') -> Dict[str, Any]:
    return {'id': id_, 'label': label, 'value': round(value, 2), 'icon': icon, 'format': fmt}


def _build_kpi_drill_data(
    sales: Dict[str, Any],
    purchase: Dict[str, Any],
    stock_pos: Dict[str, Any],
    grn_amt: float,
    grn_cnt: int,
    issue_amt: float,
    issue_cnt: int,
    adj_amt: float,
    adj_cnt: int,
) -> Dict[str, Any]:
    receivables: List[Dict[str, Any]] = []
    try:
        for row in get_accounts_receivable_summary() or []:
            bal = _f(row.get('receivable_balance') or row.get('balance'))
            if abs(bal) < 0.01:
                continue
            receivables.append({
                'code': row.get('customercode'),
                'name': row.get('customername') or '',
                'balance': round(bal, 2),
                'account': row.get('receivableaccount') or '',
                'source': row.get('balance_source') or '',
            })
        receivables.sort(key=lambda x: abs(x['balance']), reverse=True)
    except Exception:
        pass

    payables: List[Dict[str, Any]] = []
    try:
        for row in get_accounts_payable_summary() or []:
            bal = _f(row.get('payable_balance') or row.get('balance'))
            if abs(bal) < 0.01:
                continue
            payables.append({
                'code': row.get('suppliercode'),
                'name': row.get('suppliername') or '',
                'balance': round(bal, 2),
                'account': row.get('payableaccount') or '',
                'source': row.get('balance_source') or '',
            })
        payables.sort(key=lambda x: abs(x['balance']), reverse=True)
    except Exception:
        pass

    return {
        'sales': sales,
        'purchase': purchase,
        'stock_position': stock_pos,
        'stock_movement': {
            'grn_amount': round(grn_amt, 2),
            'grn_count': grn_cnt,
            'issue_amount': round(issue_amt, 2),
            'issue_count': issue_cnt,
            'adjustment_amount': round(adj_amt, 2),
            'adjustment_count': adj_cnt,
        },
        'receivables': receivables[:100],
        'payables': payables[:100],
    }


def _is_mobile_profile(raw: Dict[str, Any]) -> bool:
    profile = str(raw.get('profile') or '').strip().lower()
    if profile in ('mobile', 'light', 'fast'):
        return True
    flag = raw.get('mobile_light')
    return str(flag).strip().lower() in ('1', 'true', 'yes', 'y')


def build_business_summary_dashboard(raw: Dict[str, Any]) -> Dict[str, Any]:
    _reset_sales_ctx()
    filters = parse_business_summary_filters(raw)
    loc = filters.get('branch')
    warnings: List[str] = []
    mobile_light = _is_mobile_profile(raw)
    try:
        return _build_business_summary_dashboard_inner(filters, loc, warnings, mobile_light=mobile_light)
    except Exception as exc:
        warnings.append(str(exc)[:200])
        return _empty_business_summary_dashboard(filters, warnings)


def _empty_business_summary_dashboard(filters: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    sales = {k: 0.0 for k in ('total_sales', 'sales_return', 'net_sales', 'cash_sales', 'credit_sales')}
    sales.update({'sales_count': 0, 'return_count': 0})
    purchase = {k: 0.0 for k in ('total_purchases', 'purchase_return', 'net_purchases')}
    purchase.update({'purchase_count': 0, 'return_count': 0})
    kpis = [
        _kpi('total_sales', 'Total Sales', 0, 'bi-cart-check'),
        _kpi('sales_return', 'Sales Return', 0, 'bi-arrow-return-left'),
        _kpi('net_sales', 'Net Sales', 0, 'bi-graph-up-arrow'),
        _kpi('total_purchases', 'Total Purchases', 0, 'bi-bag-plus'),
        _kpi('purchase_return', 'Purchase Return', 0, 'bi-arrow-left-right'),
        _kpi('net_purchases', 'Net Purchases', 0, 'bi-basket'),
        _kpi('gross_profit', 'Gross Profit', 0, 'bi-currency-dollar'),
        _kpi('gross_margin_pct', 'Gross Margin %', 0, 'bi-percent', 'percent'),
        _kpi('inventory_value', 'Inventory Value', 0, 'bi-box-seam'),
        _kpi('current_stock_qty', 'Current Stock Qty', 0, 'bi-boxes', 'number'),
        _kpi('opening_stock', 'Opening Stock', 0, 'bi-door-open'),
        _kpi('closing_stock', 'Closing Stock', 0, 'bi-door-closed'),
        _kpi('stock_adjustment', 'Stock Adjustment', 0, 'bi-sliders'),
        _kpi('goods_received', 'Goods Received (GRN)', 0, 'bi-truck'),
        _kpi('goods_issued', 'Goods Issued', 0, 'bi-box-arrow-right'),
        _kpi('customer_receipts', 'Customer Receipts', 0, 'bi-cash-coin'),
        _kpi('supplier_payments', 'Supplier Payments', 0, 'bi-credit-card'),
        _kpi('expenses', 'Expenses', 0, 'bi-receipt'),
        _kpi('cash_sales', 'Cash Sales', 0, 'bi-cash'),
        _kpi('credit_sales', 'Credit Sales', 0, 'bi-credit-card-2-front'),
        _kpi('outstanding_receivables', 'Outstanding Receivables', 0, 'bi-person-lines-fill'),
        _kpi('outstanding_payables', 'Outstanding Payables', 0, 'bi-building'),
    ]
    return {
        'success': True,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'filters': filters,
        'warnings': warnings,
        'sales_source': '',
        'kpis': kpis,
        'charts': {
            'sales_vs_purchase_trend': {'labels': [], 'sales': [], 'purchase': []},
            'sales_vs_gross_profit': {'labels': ['Net Sales', 'Gross Profit'], 'values': [0, 0]},
            'daily_sales_trend': [],
            'category_sales': [],
            'brand_sales': [],
            'top_items': [],
            'top_customers': [],
            'top_suppliers': [],
            'payment_methods': [],
            'stock_movement': {'labels': ['GRN In', 'Goods Issue', 'Adjustment'], 'in': [0, 0, 0], 'out': [0, 0, 0]},
        },
        'transaction_summary': [],
        'inventory': {},
        'financial': {},
        'kpi_drill': _build_kpi_drill_data(sales, purchase, {}, 0, 0, 0, 0, 0, 0),
    }


def _build_business_summary_dashboard_inner(
    filters: Dict[str, Any],
    loc: Optional[int],
    warnings: List[str],
    *,
    mobile_light: bool = False,
) -> Dict[str, Any]:
    sales_ctx = _get_sales_ctx()
    if not sales_ctx.get('valid'):
        warnings.append('Sales tables (BILLHDR / BILLDTL) not found or missing date/amount columns.')
    sales = _sales_metrics(filters)
    purchase = _purchase_metrics(filters)
    grn_amt, grn_cnt, issue_amt, issue_cnt = _grn_metrics(filters)
    adj_amt, adj_cnt = _stock_adjustment_metrics(filters)
    if mobile_light:
        stock_pos = {'opening_stock': 0.0, 'closing_stock': 0.0, 'opening_qty': 0.0, 'closing_qty': 0.0}
        inventory = _inventory_snapshot_light(loc)
    else:
        stock_pos = _stock_position_metrics(filters)
        inventory = _inventory_snapshot(loc)
    ar, ap = _outstanding_totals()
    receipts, expense_total = _collections_payments(filters)
    supplier_payments = _supplier_payments_total(filters)

    gross_profit = 0.0
    cogs = 0.0
    gross_margin_pct = 0.0
    net_profit = 0.0
    if mobile_light:
        gross_profit = max(0.0, sales['net_sales'] - purchase['net_purchases'])
        if sales['net_sales']:
            gross_margin_pct = round(gross_profit / sales['net_sales'] * 100, 2)
        cogs = max(0.0, sales['net_sales'] - gross_profit)
        net_profit = gross_profit - expense_total
    else:
        try:
            margin_payload = build_gross_margin_dashboard({
                'date_from': filters['date_from'],
                'date_to': filters['date_to'],
                'locationcode': loc or '',
            })
        except Exception as exc:
            margin_payload = {}
            warnings.append(f'Gross margin unavailable: {str(exc)[:120]}')
        margin_kpis = margin_payload.get('kpis') or {}
        gross_profit = _f(margin_kpis.get('gross_profit'))
        cogs = _f(margin_kpis.get('cogs') or margin_kpis.get('cost_of_goods'))
        gross_margin_pct = _f(margin_kpis.get('margin_pct'))
        if not gross_margin_pct and sales['net_sales']:
            gross_margin_pct = round(gross_profit / sales['net_sales'] * 100, 2)

        try:
            pl = get_profit_and_loss_report(filters['date_from'], filters['date_to'])
        except Exception:
            pl = {}
            warnings.append('Profit & loss report unavailable for this period.')
        net_profit = _f((pl or {}).get('net_profit') or (pl or {}).get('net_income'))

    opening_stock = stock_pos.get('opening_stock', 0.0)
    closing_stock = stock_pos.get('closing_stock', 0.0)
    if not mobile_light and opening_stock == 0 and closing_stock == 0:
        opening_stock = inventory.get('inventory_value', 0) * 0.95
        closing_stock = inventory.get('inventory_value', 0)

    kpis = [
        _kpi('total_sales', 'Total Sales', sales['total_sales'], 'bi-cart-check'),
        _kpi('sales_return', 'Sales Return', sales['sales_return'], 'bi-arrow-return-left'),
        _kpi('net_sales', 'Net Sales', sales['net_sales'], 'bi-graph-up-arrow'),
        _kpi('total_purchases', 'Total Purchases', purchase['total_purchases'], 'bi-bag-plus'),
        _kpi('purchase_return', 'Purchase Return', purchase['purchase_return'], 'bi-arrow-left-right'),
        _kpi('net_purchases', 'Net Purchases', purchase['net_purchases'], 'bi-basket'),
        _kpi('gross_profit', 'Gross Profit', gross_profit, 'bi-currency-dollar'),
        _kpi('gross_margin_pct', 'Gross Margin %', gross_margin_pct, 'bi-percent', 'percent'),
        _kpi('inventory_value', 'Inventory Value', inventory.get('inventory_value', 0), 'bi-box-seam'),
        _kpi('current_stock_qty', 'Current Stock Qty', inventory.get('current_stock_qty', 0), 'bi-boxes', 'number'),
        _kpi('opening_stock', 'Opening Stock', opening_stock, 'bi-door-open'),
        _kpi('closing_stock', 'Closing Stock', closing_stock, 'bi-door-closed'),
        _kpi('stock_adjustment', 'Stock Adjustment', adj_amt, 'bi-sliders'),
        _kpi('goods_received', 'Goods Received (GRN)', grn_amt, 'bi-truck'),
        _kpi('goods_issued', 'Goods Issued', issue_amt, 'bi-box-arrow-right'),
        _kpi('customer_receipts', 'Customer Receipts', receipts, 'bi-cash-coin'),
        _kpi('supplier_payments', 'Supplier Payments', supplier_payments, 'bi-credit-card'),
        _kpi('expenses', 'Expenses', expense_total, 'bi-receipt'),
        _kpi('cash_sales', 'Cash Sales', sales['cash_sales'], 'bi-cash'),
        _kpi('credit_sales', 'Credit Sales', sales['credit_sales'], 'bi-credit-card-2-front'),
        _kpi('outstanding_receivables', 'Outstanding Receivables', ar, 'bi-person-lines-fill'),
        _kpi('outstanding_payables', 'Outstanding Payables', ap, 'bi-building'),
    ]

    tx_rows = [
        ('Sales', sales['sales_count'], sales['total_sales']),
        ('Sales Return', sales['return_count'], sales['sales_return']),
        ('Purchase', purchase['purchase_count'], purchase['total_purchases']),
        ('Purchase Return', purchase['return_count'], purchase['purchase_return']),
        ('Stock Adjustment', adj_cnt, adj_amt),
        ('Goods Receipt', grn_cnt, grn_amt),
        ('Goods Issue', issue_cnt, issue_amt),
        ('Expenses', 0, expense_total),
    ]
    tx_total = sum(r[2] for r in tx_rows) or 1.0
    transaction_summary = [
        {
            'transaction': name,
            'count': cnt,
            'amount': round(amt, 2),
            'percentage': round(amt / tx_total * 100, 1),
        }
        for name, cnt, amt in tx_rows
    ]

    sales_trend = _daily_trend(filters, 'sales')
    purchase_trend = _daily_trend(filters, 'purchase')
    dates = sorted({x['date'] for x in sales_trend + purchase_trend})
    sales_map = {x['date']: x['amount'] for x in sales_trend}
    purch_map = {x['date']: x['amount'] for x in purchase_trend}

    charts = {
        'sales_vs_purchase_trend': {
            'labels': dates,
            'sales': [sales_map.get(d, 0) for d in dates],
            'purchase': [purch_map.get(d, 0) for d in dates],
        },
        'sales_vs_gross_profit': {
            'labels': ['Net Sales', 'Gross Profit'],
            'values': [round(sales['net_sales'], 2), round(gross_profit, 2)],
        },
        'daily_sales_trend': sales_trend,
        'category_sales': _top_entities(filters, 'categories', 8),
        'brand_sales': [] if mobile_light else _top_entities(filters, 'brands', 8),
        'top_items': _top_entities(filters, 'items', 10),
        'top_customers': _top_entities(filters, 'customers', 10),
        'top_suppliers': [] if mobile_light else _top_entities(filters, 'suppliers', 10),
        'payment_methods': _payment_distribution(filters),
        'stock_movement': {
            'labels': ['GRN In', 'Goods Issue', 'Adjustment'],
            'in': [round(grn_amt, 2), 0, round(adj_amt, 2)],
            'out': [0, round(issue_amt, 2), 0],
        },
    }

    financial = {
        'sales': round(sales['total_sales'], 2),
        'sales_return': round(sales['sales_return'], 2),
        'net_sales': round(sales['net_sales'], 2),
        'purchases': round(purchase['total_purchases'], 2),
        'purchase_return': round(purchase['purchase_return'], 2),
        'net_purchases': round(purchase['net_purchases'], 2),
        'purchase_source': purchase.get('purchase_source') or 'lpo',
        'cogs': round(cogs or (sales['net_sales'] - gross_profit), 2),
        'gross_profit': round(gross_profit, 2),
        'gross_profit_pct': round(gross_margin_pct, 2),
        'net_profit': round(net_profit, 2),
        'expense_total': round(expense_total, 2),
    }

    if mobile_light:
        inventory_section = {
            'inventory_value': inventory.get('inventory_value', 0),
            'current_stock_qty': inventory.get('current_stock_qty', 0),
        }
        kpi_drill: Dict[str, Any] = {}
    else:
        inventory_section = {
            'total_items': inventory.get('total_items', 0),
            'active_items': inventory.get('active_items', 0),
            'out_of_stock': inventory.get('out_of_stock', 0),
            'low_stock': inventory.get('low_stock', 0),
            'negative_stock': inventory.get('negative_stock', 0),
            'dead_stock': inventory.get('dead_stock', 0),
            'highest_value_stock': inventory.get('highest_value_stock') or [],
            'fast_moving': _top_entities(filters, 'items', 5),
            'slow_moving': [],
        }
        kpi_drill = _build_kpi_drill_data(
            sales, purchase, stock_pos, grn_amt, grn_cnt, issue_amt, issue_cnt, adj_amt, adj_cnt,
        )

    return {
        'success': True,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'filters': filters,
        'warnings': warnings,
        'sales_source': sales_ctx.get('hdr') or '',
        'kpis': kpis,
        'charts': charts,
        'transaction_summary': transaction_summary,
        'inventory': inventory_section,
        'financial': financial,
        'kpi_drill': kpi_drill,
        'profile': 'mobile' if mobile_light else 'full',
    }
