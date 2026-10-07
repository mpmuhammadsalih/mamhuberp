"""Salesman Summary report blueprint."""
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import io
from nexa_http import Blueprint, jsonify, redirect, render_template, session, request, url_for, Response
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4, landscape
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
from db import _fetch_rows, _get_table_columns, _detect_column, get_location_info_by_dbkey
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('salesman_summary', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _detect_table(candidates: list) -> str:
    """Return first table name that exists."""
    for table_name in candidates:
        try:
            if _get_table_columns(table_name):
                return table_name
        except Exception:
            continue
    return ''

@bp.route('/salesman-summary')
def salesman_summary():
    """Salesman Summary page"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('salesman_summary/salesman_summary.html', today=today)

@bp.route('/salesman-summary/sales', methods=['GET'])
def get_sales_data():
    """API endpoint to fetch sales data for salesman summary"""
    try:
        if not session.get('user'):
            return jsonify({'error': 'Not authenticated'}, 401)
        if not session.get('tenant_id'):
            return jsonify({'error': 'Database/location not assigned. Please contact IT.'}, 403)
        location_code = request.args.get('location_code')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        salesmancode = request.args.get('salesmancode')
        salesmanname = request.args.get('salesmanname', '')
        if not all([location_code, start_date, end_date]):
            return jsonify({'error': 'Missing required parameters'}, 400)
    except Exception as e:
        print(f'[ERROR get_sales_data] Error in initial setup: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Setup error: {str(e)}'}, 500)
    try:
        salesman_table = None
        for table_name in ['SALESMAN', 'salesman', 'SALESMEN', 'salesmen']:
            try:
                cols = _get_table_columns(table_name)
                if 'SALESMANCODE' in cols or 'salesmancode' in cols:
                    salesman_table = table_name
                    break
            except Exception:
                continue
        if not salesman_table:
            return jsonify({'error': 'Salesman table not found'}, 500)
        salesmancode_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        salesmanname_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
        if not salesmancode_col:
            return jsonify({'error': 'Salesman code column not found'}, 500)
        tempsettlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        salesmansettlement_table = _detect_table(['TBLSALESMANSETTLEMENT', 'tblsalesmansettlement'])
        salesmanopening_table = _detect_table(['SALESMANOPENING', 'salesmanopening'])
        billhdrhistory_table = _detect_table(['BILLHDRHISTORY', 'billhdrhistory'])
        temp_salesmancode_col = None
        temp_billdate_col = None
        temp_billamount_col = None
        temp_paidamount_col = None
        temp_paiddate_col = None
        temp_flag_col = None
        temp_locationcode_col = None
        if tempsettlement_table:
            temp_salesmancode_col = _detect_column(tempsettlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE'])
            temp_billdate_col = _detect_column(tempsettlement_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT'])
            temp_billamount_col = _detect_column(tempsettlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'AMOUNT'])
            temp_paidamount_col = _detect_column(tempsettlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID'])
            temp_paiddate_col = _detect_column(tempsettlement_table, ['PAIDDATE', 'PAID_DATE', 'PAIDATE', 'PAYMENTDATE'])
            temp_flag_col = _detect_column(tempsettlement_table, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG'])
            temp_locationcode_col = _detect_column(tempsettlement_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        temp_location_filter = f' AND {temp_locationcode_col} = :location_code' if temp_locationcode_col and location_code else ''
        sm_settle_salesmancode_col = None
        sm_settle_voucherdate_col = None
        sm_settle_voucheramount_col = None
        sm_settle_remarks_col = None
        sm_settle_locationcode_col = None
        if salesmansettlement_table:
            sm_settle_salesmancode_col = _detect_column(salesmansettlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE'])
            sm_settle_voucherdate_col = _detect_column(salesmansettlement_table, ['VOUCHERDATE', 'VOUCHER_DATE', 'VOUCHERDT', 'VOUCHER_DT', 'VOUCHERDATE', 'VOUCHERDATE'])
            sm_settle_voucheramount_col = _detect_column(salesmansettlement_table, ['VOUCHERAMOUNT', 'VOUCHER_AMOUNT', 'AMOUNT', 'VOUCHERAMT'])
            sm_settle_remarks_col = _detect_column(salesmansettlement_table, ['REMARKS', 'REMARK', 'NOTE', 'NOTES'])
            sm_settle_locationcode_col = _detect_column(salesmansettlement_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        sm_settle_location_filter = f' AND {sm_settle_locationcode_col} = :location_code' if sm_settle_locationcode_col and location_code else ''
        opening_salesmancode_col = None
        opening_billdate_col = None
        opening_amount_col = None
        opening_locationcode_col = None
        if salesmanopening_table:
            opening_salesmancode_col = _detect_column(salesmanopening_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE'])
            opening_billdate_col = _detect_column(salesmanopening_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT'])
            opening_amount_col = _detect_column(salesmanopening_table, ['AMOUNT', 'AMT', 'OPENINGAMOUNT', 'OPENING_AMOUNT'])
            opening_locationcode_col = _detect_column(salesmanopening_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        history_salesmancode_col = None
        history_billdate_col = None
        history_netbillamount_col = None
        history_billtype_col = None
        history_locationcode_col = None
        if billhdrhistory_table:
            history_salesmancode_col = _detect_column(billhdrhistory_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE'])
            history_billdate_col = _detect_column(billhdrhistory_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT'])
            history_netbillamount_col = _detect_column(billhdrhistory_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_AMOUNT'])
            history_billtype_col = _detect_column(billhdrhistory_table, ['BILLTYPE', 'BILL_TYPE', 'TYPE'])
            history_locationcode_col = _detect_column(billhdrhistory_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        history_location_filter = f' AND {history_locationcode_col} = :location_code' if history_locationcode_col and location_code else ''
        closingcredit_col = _detect_column(salesman_table, ['OUTSTANDINGAMOUNT', 'OUTSTANDING_AMOUNT', 'CLOSINGCREDIT', 'CLOSING_CREDIT', 'OUTSTANDING'])
        salesman_locationcode_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        salesman_location_filter = f' AND S.{salesman_locationcode_col} = :location_code' if salesman_locationcode_col and location_code else ''
        closingcredit_location_filter = f' WHERE {salesman_locationcode_col} = :location_code' if salesman_locationcode_col and location_code else ''
        query_parts = [f'S.{salesmancode_col} AS salesmancode', f'S.{salesmanname_col} AS salesmanname']
        if tempsettlement_table and temp_salesmancode_col and temp_billdate_col and temp_billamount_col and temp_paidamount_col:
            query_parts.append('NVL(A.OPCREDIT, 0) AS opcredit')
            opcredit_join = f"\n        LEFT OUTER JOIN (\n            SELECT {temp_salesmancode_col} AS SALESMANCODE,\n                   SUM({temp_billamount_col} - NVL({temp_paidamount_col}, 0)) AS OPCREDIT\n            FROM {tempsettlement_table}\n            WHERE {temp_billdate_col} < TO_DATE(:start_date, 'YYYY-MM-DD'){temp_location_filter}\n            GROUP BY {temp_salesmancode_col}\n        ) A ON S.{salesmancode_col} = A.SALESMANCODE"
        else:
            query_parts.append('0 AS opcredit')
            opcredit_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(B.CASHSALES, 0) AS cashsales')
            cashsales_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASHSALES\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} <> 'R'\n              AND {history_netbillamount_col} > 0\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) B ON S.{salesmancode_col} = B.SALESMANCODE"
        else:
            query_parts.append('0 AS cashsales')
            cashsales_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(C.CASHGRV, 0) AS cashgrv')
            cashgrv_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASHGRV\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} < 0\n              AND {history_billtype_col} <> 'R'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) C ON S.{salesmancode_col} = C.SALESMANCODE"
        else:
            query_parts.append('0 AS cashgrv')
            cashgrv_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(X.CREDITSALES, 0) AS creditsales')
            creditsales_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CREDITSALES\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} = 'R'\n              AND {history_netbillamount_col} > 0\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) X ON S.{salesmancode_col} = X.SALESMANCODE"
        else:
            query_parts.append('0 AS creditsales')
            creditsales_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(G.CREDITGRV, 0) AS creditgrv')
            creditgrv_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CREDITGRV\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} < 0\n              AND {history_billtype_col} = 'R'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) G ON S.{salesmancode_col} = G.SALESMANCODE"
        else:
            query_parts.append('0 AS creditgrv')
            creditgrv_join = ''
        tmpcollection_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
        tmpcollection_salesmancode_col = None
        tmpcollection_billdate_col = None
        tmpcollection_collection_col = None
        tmpcollection_locationcode_col = None
        if tmpcollection_table:
            tmpcollection_salesmancode_col = _detect_column(tmpcollection_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
            tmpcollection_billdate_col = _detect_column(tmpcollection_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
            tmpcollection_collection_col = _detect_column(tmpcollection_table, ['COLLECTION', 'collection', 'COLLECTIONAMOUNT', 'collectionamount'])
            tmpcollection_locationcode_col = _detect_column(tmpcollection_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
        if tmpcollection_table and tmpcollection_salesmancode_col and tmpcollection_billdate_col and tmpcollection_collection_col:
            location_filter = ''
            if tmpcollection_locationcode_col and location_code:
                location_filter = f' AND {tmpcollection_locationcode_col} = :location_code'
            query_parts.append('NVL(TMPCOL.TMPCOLLECTION, 0) AS tmpcollection')
            tmpcollection_join = f"\n        LEFT OUTER JOIN (\n            SELECT {tmpcollection_salesmancode_col} AS SALESMANCODE,\n                   SUM({tmpcollection_collection_col}) AS TMPCOLLECTION\n            FROM {tmpcollection_table}\n            WHERE {tmpcollection_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n            {location_filter}\n            GROUP BY {tmpcollection_salesmancode_col}\n        ) TMPCOL ON S.{salesmancode_col} = TMPCOL.SALESMANCODE"
        else:
            query_parts.append('0 AS tmpcollection')
            tmpcollection_join = ''
        if tempsettlement_table and temp_salesmancode_col and temp_paiddate_col and temp_paidamount_col and temp_flag_col:
            query_parts.append('NVL(D.COLLECTION, 0) AS collection')
            collection_join = f"\n        LEFT OUTER JOIN (\n            SELECT {temp_salesmancode_col} AS SALESMANCODE,\n                   SUM({temp_paidamount_col}) AS COLLECTION\n            FROM {tempsettlement_table}\n            WHERE {temp_flag_col} = 'R'\n              AND {temp_paiddate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){temp_location_filter}\n            GROUP BY {temp_salesmancode_col}\n        ) D ON S.{salesmancode_col} = D.SALESMANCODE"
        else:
            query_parts.append('0 AS collection')
            collection_join = ''
        if salesmansettlement_table and sm_settle_salesmancode_col and sm_settle_voucherdate_col and sm_settle_voucheramount_col and sm_settle_remarks_col:
            query_parts.append('NVL(H.SHORT, 0) AS short')
            short_join = f"\n        LEFT OUTER JOIN (\n            SELECT {sm_settle_salesmancode_col} AS SALESMANCODE,\n                   SUM({sm_settle_voucheramount_col}) AS SHORT\n            FROM {salesmansettlement_table}\n            WHERE {sm_settle_remarks_col} <> 'CASH DISCOUNT'\n              AND {sm_settle_voucherdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){sm_settle_location_filter}\n            GROUP BY {sm_settle_salesmancode_col}\n        ) H ON S.{salesmancode_col} = H.SALESMANCODE"
        else:
            query_parts.append('0 AS short')
            short_join = ''
        if salesmansettlement_table and sm_settle_salesmancode_col and sm_settle_voucherdate_col and sm_settle_voucheramount_col and sm_settle_remarks_col:
            query_parts.append('NVL(Z.DISCOUNT, 0) AS discount')
            discount_join = f"\n        LEFT OUTER JOIN (\n            SELECT {sm_settle_salesmancode_col} AS SALESMANCODE,\n                   SUM({sm_settle_voucheramount_col}) AS DISCOUNT\n            FROM {salesmansettlement_table}\n            WHERE {sm_settle_remarks_col} = 'CASH DISCOUNT'\n              AND {sm_settle_voucherdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){sm_settle_location_filter}\n            GROUP BY {sm_settle_salesmancode_col}\n        ) Z ON S.{salesmancode_col} = Z.SALESMANCODE"
        else:
            query_parts.append('0 AS discount')
            discount_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(E.CASH, 0) AS cash')
            cash_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASH\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} = 'C'\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) E ON S.{salesmancode_col} = E.SALESMANCODE"
        else:
            query_parts.append('0 AS cash')
            cash_join = ''
        if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col:
            query_parts.append('NVL(T.TEMP, 0) AS temp')
            temp_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS TEMP\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} > 0\n              AND {history_billtype_col} = 'T'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) T ON S.{salesmancode_col} = T.SALESMANCODE"
        else:
            query_parts.append('0 AS temp')
            temp_join = ''
        if closingcredit_col:
            query_parts.append(f'NVL(I.CLOSINGCREDIT, 0) AS closingcredit')
            closingcredit_join = f'\n        LEFT OUTER JOIN (\n            SELECT {salesmancode_col} AS SALESMANCODE,\n                   {closingcredit_col} AS CLOSINGCREDIT\n            FROM {salesman_table}{closingcredit_location_filter}\n        ) I ON S.{salesmancode_col} = I.SALESMANCODE'
        else:
            query_parts.append('0 AS closingcredit')
            closingcredit_join = ''
        query_parts.append('0 AS redemption')
        redemption_join = ''
        where_conditions = []
        params = {'location_code': location_code, 'start_date': start_date, 'end_date': end_date}
        if salesman_locationcode_col and location_code:
            where_conditions.append(f'S.{salesman_locationcode_col} = :location_code')
        if salesmancode:
            where_conditions.append(f'S.{salesmancode_col} = :salesmancode')
            params['salesmancode'] = salesmancode
        if salesmanname and salesmanname_col:
            where_conditions.append(f'S.{salesmanname_col} LIKE :salesmanname')
            params['salesmanname'] = f'%{salesmanname}%'
        where_clause = ''
        if where_conditions:
            where_clause = ' WHERE ' + ' AND '.join(where_conditions)
        query = f"\n        SELECT {', '.join(query_parts)}\n        FROM {salesman_table} S\n        {opcredit_join}\n        {cashsales_join}\n        {cashgrv_join}\n        {creditsales_join}\n        {creditgrv_join}\n        {tmpcollection_join}\n        {collection_join}\n        {short_join}\n        {discount_join}\n        {cash_join}\n        {temp_join}\n        {closingcredit_join}\n        {redemption_join}{where_clause}\n        ORDER BY S.{salesmancode_col} ASC\n        "
        return _process_salesman_summary_data(query, params, salesmanopening_table, opening_salesmancode_col, opening_billdate_col, opening_amount_col, opening_locationcode_col, start_date, salesmancode, salesmanname, salesmancode_col, salesmanname_col, return_json=True)
    except Exception as e:
        print(f'[ERROR get_sales_data] Error in query building or execution: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error fetching sales data: {str(e)}'}, 500)

def _process_salesman_summary_data(query: str, params: Dict[str, Any], salesmanopening_table: Optional[str], opening_salesmancode_col: Optional[str], opening_billdate_col: Optional[str], opening_amount_col: Optional[str], opening_locationcode_col: Optional[str], start_date: str, salesmancode: Optional[str], salesmanname: str, salesmancode_col: str, salesmanname_col: Optional[str], return_json: bool=False) -> Any:
    """Process salesman summary data - shared by get_sales_data and PDF generation"""
    try:
        _, rows = _fetch_rows(query, params)
        opening_map = {}
        if rows and salesmanopening_table and opening_salesmancode_col and opening_billdate_col and opening_amount_col:
            salesmancodes = []
            for row in rows:
                code = row.get('salesmancode')
                if code:
                    code_str = str(code).strip()
                    if code_str and code_str.replace('_', '').replace('-', '').isalnum():
                        salesmancodes.append(code_str)
            if salesmancodes:
                placeholders = []
                params_dict = {'start_date': start_date}
                for idx, code in enumerate(salesmancodes):
                    placeholder = f':code{idx}'
                    placeholders.append(placeholder)
                    params_dict[f'code{idx}'] = code
                if opening_locationcode_col and params.get('location_code'):
                    params_dict['location_code'] = params['location_code']
                opening_location_filter = f' AND {opening_locationcode_col} = :location_code' if opening_locationcode_col and params.get('location_code') else ''
                opening_query = f"\n                    SELECT {opening_salesmancode_col} AS salesmancode,\n                           SUM({opening_amount_col}) AS amount\n                    FROM {salesmanopening_table}\n                    WHERE {opening_salesmancode_col} IN ({', '.join(placeholders)})\n                      AND {opening_billdate_col} < TO_DATE(:start_date, 'YYYY-MM-DD'){opening_location_filter}\n                    GROUP BY {opening_salesmancode_col}\n                "
                try:
                    _, opening_rows = _fetch_rows(opening_query, params_dict)
                    for opening_row in opening_rows:
                        code = str(opening_row.get('salesmancode', ''))
                        amount = float(opening_row.get('amount', 0) or 0) * -1
                        opening_map[code] = amount
                except Exception:
                    pass
        data = []
        for row in rows:
            salesmancode_val = str(row.get('salesmancode', ''))
            opening = opening_map.get(salesmancode_val, 0.0)
            opcredit = float(row.get('opcredit', 0) or 0)
            cashsales = float(row.get('cashsales', 0) or 0)
            cashgrv = float(row.get('cashgrv', 0) or 0)
            creditsales = float(row.get('creditsales', 0) or 0)
            creditgrv = float(row.get('creditgrv', 0) or 0)
            temp = float(row.get('temp', 0) or 0)
            short = float(row.get('short', 0) or 0)
            tmpcollection = float(row.get('tmpcollection', 0) or 0)
            collection = float(row.get('collection', 0) or 0)
            discount = float(row.get('discount', 0) or 0)
            cash = float(row.get('cash', 0) or 0)
            closingcredit = float(row.get('closingcredit', 0) or 0)
            redemption = float(row.get('redemption', 0) or 0)
            calc_col13 = collection + cash - short - discount
            calc_col14 = opening + creditsales + short - collection
            voucher = redemption
            if abs(calc_col14) <= 0.01:
                continue
            data.append({'salesmancode': salesmancode_val, 'salesmanname': str(row.get('salesmanname', '')), 'opening': opening, 'opcredit': opcredit, 'cashsales': cashsales, 'cashgrv': cashgrv, 'creditsales': creditsales, 'creditgrv': creditgrv, 'temp': temp, 'short': short, 'tmpcollection': tmpcollection, 'collection': collection, 'discount': discount, 'cash': cash, 'closingcredit': closingcredit, 'calc_col13': calc_col13, 'calc_col14': calc_col14, 'voucher': voucher})
        if return_json:
            return jsonify({'status': 'success', 'data': data})
        return data
    except Exception as e:
        print(f'[ERROR _process_salesman_summary_data] {e}')
        import traceback
        traceback.print_exc()
        if return_json:
            return jsonify({'error': str(e)}, 500)
        raise

def _generate_salesman_summary_pdf(data: List[Dict[str, Any]], start_date: str, end_date: str, location_name: str='') -> Optional[bytes]:
    """Generate PDF report for salesman summary in landscape orientation with small font."""
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        from reportlab.lib.pagesizes import landscape as landscape_func
        page_size = landscape_func(A4)
        doc = SimpleDocTemplate(buffer, pagesize=page_size, topMargin=0.4 * inch, bottomMargin=0.4 * inch, leftMargin=0.3 * inch, rightMargin=0.3 * inch)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#1f2937'), spaceAfter=8, alignment=TA_CENTER)
        title = Paragraph('Salesman Summary Report', title_style)
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))
        details_data = [['Location:', location_name or 'N/A'], ['Date From:', start_date], ['Date To:', end_date]]
        details_table = Table(details_data, colWidths=[1.5 * inch, 3 * inch])
        details_table.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        story.append(details_table)
        story.append(Spacer(1, 0.15 * inch))
        headers = ['No', 'Code', 'Salesman Name', 'Op.balance', 'Cash Sales', 'Cash GRV', 'Credit Sales', 'Credit GRV', 'Tmp Credit', 'Disc', 'Short', 'Tmp.Collection', 'Collection', 'Total Cash', 'cl.Balance', 'Voucher']
        table_data = [headers]
        wrap_style = ParagraphStyle('WrapStyle', parent=styles['Normal'], fontSize=6, leading=7, wordWrap='CJK')
        for idx, row in enumerate(data, 1):
            salesman_name = str(row.get('salesmanname', ''))
            salesman_name_display = Paragraph(salesman_name, wrap_style) if len(salesman_name) > 20 else salesman_name
            table_data.append([str(idx), str(row.get('salesmancode', '')), salesman_name_display, f"{float(row.get('opening', 0) or 0):.2f}", f"{float(row.get('cashsales', 0) or 0):.2f}", f"{float(row.get('cashgrv', 0) or 0):.2f}", f"{float(row.get('creditsales', 0) or 0):.2f}", f"{float(row.get('creditgrv', 0) or 0):.2f}", f"{float(row.get('temp', 0) or 0):.2f}", f"{float(row.get('discount', 0) or 0):.2f}", f"{float(row.get('short', 0) or 0):.2f}", f"{float(row.get('tmpcollection', 0) or 0):.2f}", f"{float(row.get('collection', 0) or 0):.2f}", f"{float(row.get('calc_col13', 0) or 0):.2f}", f"{float(row.get('calc_col14', 0) or 0):.2f}", f"{float(row.get('voucher', 0) or 0):.2f}"])
        if data:
            totals = {'opening': sum((float(row.get('opening', 0) or 0) for row in data)), 'cashsales': sum((float(row.get('cashsales', 0) or 0) for row in data)), 'cashgrv': sum((float(row.get('cashgrv', 0) or 0) for row in data)), 'creditsales': sum((float(row.get('creditsales', 0) or 0) for row in data)), 'creditgrv': sum((float(row.get('creditgrv', 0) or 0) for row in data)), 'temp': sum((float(row.get('temp', 0) or 0) for row in data)), 'discount': sum((float(row.get('discount', 0) or 0) for row in data)), 'short': sum((float(row.get('short', 0) or 0) for row in data)), 'tmpcollection': sum((float(row.get('tmpcollection', 0) or 0) for row in data)), 'collection': sum((float(row.get('collection', 0) or 0) for row in data)), 'calc_col13': sum((float(row.get('calc_col13', 0) or 0) for row in data)), 'calc_col14': sum((float(row.get('calc_col14', 0) or 0) for row in data)), 'voucher': sum((float(row.get('voucher', 0) or 0) for row in data))}
            table_data.append(['Totals', '', '', f"{totals['opening']:.2f}", f"{totals['cashsales']:.2f}", f"{totals['cashgrv']:.2f}", f"{totals['creditsales']:.2f}", f"{totals['creditgrv']:.2f}", f"{totals['temp']:.2f}", f"{totals['discount']:.2f}", f"{totals['short']:.2f}", f"{totals['tmpcollection']:.2f}", f"{totals['collection']:.2f}", f"{totals['calc_col13']:.2f}", f"{totals['calc_col14']:.2f}", f"{totals['voucher']:.2f}"])
        col_widths = [0.4 * inch, 0.5 * inch, 1.2 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.5 * inch, 0.5 * inch, 0.7 * inch, 0.6 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.black), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 7), ('ALIGN', (0, 0), (-1, 0), 'CENTER'), ('BOTTOMPADDING', (0, 0), (-1, 0), 6), ('TOPPADDING', (0, 0), (-1, 0), 6), ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'), ('FONTSIZE', (0, 1), (-1, -2), 6), ('ALIGN', (0, 1), (0, -2), 'CENTER'), ('ALIGN', (1, 1), (1, -2), 'LEFT'), ('ALIGN', (2, 1), (2, -2), 'LEFT'), ('ALIGN', (3, 1), (-1, -2), 'RIGHT'), ('VALIGN', (0, 1), (-1, -2), 'TOP'), ('BOTTOMPADDING', (0, 1), (-1, -2), 3), ('TOPPADDING', (0, 1), (-1, -2), 3), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fafb')]), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f093fb')), ('TEXTCOLOR', (0, -1), (-1, -1), colors.black), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, -1), (-1, -1), 7), ('ALIGN', (0, -1), (2, -1), 'LEFT'), ('ALIGN', (3, -1), (-1, -1), 'RIGHT'), ('BOTTOMPADDING', (0, -1), (-1, -1), 6), ('TOPPADDING', (0, -1), (-1, -1), 6), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')), ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#374151')), ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#374151'))]))
        story.append(tbl)
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f'[ERROR _generate_salesman_summary_pdf] {e}')
        import traceback
        traceback.print_exc()
        return None

@bp.route('/salesman-summary/report', methods=['GET'])
def generate_salesman_summary_report():
    """Generate PDF report for salesman summary"""
    if not session.get('user'):
        return Response('Not authenticated', status=401, mimetype='text/plain')
    location_code = request.args.get('location_code')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    salesmancode = request.args.get('salesmancode')
    salesmanname = request.args.get('salesmanname', '')
    if not all([location_code, start_date, end_date]):
        return Response('Missing required parameters', status=400, mimetype='text/plain')
    dbkey = session.get('tenant_id')
    location_name = ''
    try:
        loc_info = get_location_info_by_dbkey(dbkey)
        if loc_info:
            location_name = (loc_info.get('locationname') or '').strip()
    except Exception:
        pass
    try:
        salesman_table = None
        for table_name in ['SALESMAN', 'salesman', 'SALESMEN', 'salesmen']:
            try:
                cols = _get_table_columns(table_name)
                if 'SALESMANCODE' in cols or 'salesmancode' in cols:
                    salesman_table = table_name
                    break
            except Exception:
                continue
        if not salesman_table:
            return Response('Salesman table not found', status=500, mimetype='text/plain')
        salesmancode_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code'])
        salesmanname_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name'])
        if not salesmancode_col:
            return Response('Salesman code column not found', status=500, mimetype='text/plain')
        tempsettlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        salesmansettlement_table = _detect_table(['TBLSALESMANSETTLEMENT', 'tblsalesmansettlement'])
        salesmanopening_table = _detect_table(['SALESMANOPENING', 'salesmanopening'])
        billhdrhistory_table = _detect_table(['BILLHDRHISTORY', 'billhdrhistory'])
        temp_salesmancode_col = _detect_column(tempsettlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE']) if tempsettlement_table else None
        temp_billdate_col = _detect_column(tempsettlement_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT']) if tempsettlement_table else None
        temp_billamount_col = _detect_column(tempsettlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'AMOUNT']) if tempsettlement_table else None
        temp_paidamount_col = _detect_column(tempsettlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'PAIDAMT', 'PAID']) if tempsettlement_table else None
        temp_paiddate_col = _detect_column(tempsettlement_table, ['PAIDDATE', 'PAID_DATE', 'PAIDATE', 'PAYMENTDATE']) if tempsettlement_table else None
        temp_flag_col = _detect_column(tempsettlement_table, ['FLAG', 'FLAG_CODE', 'STATUS_FLAG']) if tempsettlement_table else None
        temp_locationcode_col = _detect_column(tempsettlement_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if tempsettlement_table else None
        temp_location_filter = f' AND {temp_locationcode_col} = :location_code' if temp_locationcode_col and location_code else ''
        sm_settle_salesmancode_col = _detect_column(salesmansettlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE']) if salesmansettlement_table else None
        sm_settle_voucherdate_col = _detect_column(salesmansettlement_table, ['VOUCHERDATE', 'VOUCHER_DATE', 'VOUCHERDT', 'VOUCHER_DT']) if salesmansettlement_table else None
        sm_settle_voucheramount_col = _detect_column(salesmansettlement_table, ['VOUCHERAMOUNT', 'VOUCHER_AMOUNT', 'AMOUNT', 'VOUCHERAMT']) if salesmansettlement_table else None
        sm_settle_remarks_col = _detect_column(salesmansettlement_table, ['REMARKS', 'REMARK', 'NOTE', 'NOTES']) if salesmansettlement_table else None
        sm_settle_locationcode_col = _detect_column(salesmansettlement_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if salesmansettlement_table else None
        sm_settle_location_filter = f' AND {sm_settle_locationcode_col} = :location_code' if sm_settle_locationcode_col and location_code else ''
        opening_salesmancode_col = _detect_column(salesmanopening_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE']) if salesmanopening_table else None
        opening_billdate_col = _detect_column(salesmanopening_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT']) if salesmanopening_table else None
        opening_amount_col = _detect_column(salesmanopening_table, ['AMOUNT', 'AMT', 'OPENINGAMOUNT', 'OPENING_AMOUNT']) if salesmanopening_table else None
        opening_locationcode_col = _detect_column(salesmanopening_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if salesmanopening_table else None
        history_salesmancode_col = _detect_column(billhdrhistory_table, ['SALESMANCODE', 'SALESMAN_CODE', 'SMCODE', 'SM_CODE']) if billhdrhistory_table else None
        history_billdate_col = _detect_column(billhdrhistory_table, ['BILLDATE', 'BILL_DATE', 'BILLDT', 'BILL_DT']) if billhdrhistory_table else None
        history_netbillamount_col = _detect_column(billhdrhistory_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_AMOUNT']) if billhdrhistory_table else None
        history_billtype_col = _detect_column(billhdrhistory_table, ['BILLTYPE', 'BILL_TYPE', 'TYPE']) if billhdrhistory_table else None
        history_locationcode_col = _detect_column(billhdrhistory_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE']) if billhdrhistory_table else None
        history_location_filter = f' AND {history_locationcode_col} = :location_code' if history_locationcode_col and location_code else ''
        closingcredit_col = _detect_column(salesman_table, ['OUTSTANDINGAMOUNT', 'OUTSTANDING_AMOUNT', 'CLOSINGCREDIT', 'CLOSING_CREDIT', 'OUTSTANDING'])
        salesman_locationcode_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOCCODE', 'LOC_CODE'])
        closingcredit_location_filter = f' WHERE {salesman_locationcode_col} = :location_code' if salesman_locationcode_col and location_code else ''
        query_parts = [f'S.{salesmancode_col} AS salesmancode', f'S.{salesmanname_col} AS salesmanname']
        opcredit_join = f"\n        LEFT OUTER JOIN (\n            SELECT {temp_salesmancode_col} AS SALESMANCODE,\n                   SUM({temp_billamount_col} - NVL({temp_paidamount_col}, 0)) AS OPCREDIT\n            FROM {tempsettlement_table}\n            WHERE {temp_billdate_col} < TO_DATE(:start_date, 'YYYY-MM-DD'){temp_location_filter}\n            GROUP BY {temp_salesmancode_col}\n        ) A ON S.{salesmancode_col} = A.SALESMANCODE" if tempsettlement_table and temp_salesmancode_col and temp_billdate_col and temp_billamount_col and temp_paidamount_col else ''
        query_parts.append('NVL(A.OPCREDIT, 0) AS opcredit' if opcredit_join else '0 AS opcredit')
        cashsales_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASHSALES\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} <> 'R' AND {history_netbillamount_col} > 0\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) B ON S.{salesmancode_col} = B.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(B.CASHSALES, 0) AS cashsales' if cashsales_join else '0 AS cashsales')
        cashgrv_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASHGRV\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} < 0 AND {history_billtype_col} <> 'R'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) C ON S.{salesmancode_col} = C.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(C.CASHGRV, 0) AS cashgrv' if cashgrv_join else '0 AS cashgrv')
        creditsales_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CREDITSALES\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} = 'R' AND {history_netbillamount_col} > 0\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) X ON S.{salesmancode_col} = X.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(X.CREDITSALES, 0) AS creditsales' if creditsales_join else '0 AS creditsales')
        creditgrv_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CREDITGRV\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} < 0 AND {history_billtype_col} = 'R'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) G ON S.{salesmancode_col} = G.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(G.CREDITGRV, 0) AS creditgrv' if creditgrv_join else '0 AS creditgrv')
        tmpcollection_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
        tmpcollection_salesmancode_col = _detect_column(tmpcollection_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode']) if tmpcollection_table else None
        tmpcollection_billdate_col = _detect_column(tmpcollection_table, ['BILLDATE', 'BILL_DATE', 'billdate']) if tmpcollection_table else None
        tmpcollection_collection_col = _detect_column(tmpcollection_table, ['COLLECTION', 'collection', 'COLLECTIONAMOUNT', 'collectionamount']) if tmpcollection_table else None
        tmpcollection_locationcode_col = _detect_column(tmpcollection_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode']) if tmpcollection_table else None
        location_filter = f' AND {tmpcollection_locationcode_col} = :location_code' if tmpcollection_locationcode_col and location_code else ''
        tmpcollection_join = f"\n        LEFT OUTER JOIN (\n            SELECT {tmpcollection_salesmancode_col} AS SALESMANCODE,\n                   SUM({tmpcollection_collection_col}) AS TMPCOLLECTION\n            FROM {tmpcollection_table}\n            WHERE {tmpcollection_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n            {location_filter}\n            GROUP BY {tmpcollection_salesmancode_col}\n        ) TMPCOL ON S.{salesmancode_col} = TMPCOL.SALESMANCODE" if tmpcollection_table and tmpcollection_salesmancode_col and tmpcollection_billdate_col and tmpcollection_collection_col else ''
        query_parts.append('NVL(TMPCOL.TMPCOLLECTION, 0) AS tmpcollection' if tmpcollection_join else '0 AS tmpcollection')
        collection_join = f"\n        LEFT OUTER JOIN (\n            SELECT {temp_salesmancode_col} AS SALESMANCODE,\n                   SUM({temp_paidamount_col}) AS COLLECTION\n            FROM {tempsettlement_table}\n            WHERE {temp_flag_col} = 'R'\n              AND {temp_paiddate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){temp_location_filter}\n            GROUP BY {temp_salesmancode_col}\n        ) D ON S.{salesmancode_col} = D.SALESMANCODE" if tempsettlement_table and temp_salesmancode_col and temp_paiddate_col and temp_paidamount_col and temp_flag_col else ''
        query_parts.append('NVL(D.COLLECTION, 0) AS collection' if collection_join else '0 AS collection')
        short_join = f"\n        LEFT OUTER JOIN (\n            SELECT {sm_settle_salesmancode_col} AS SALESMANCODE,\n                   SUM({sm_settle_voucheramount_col}) AS SHORT\n            FROM {salesmansettlement_table}\n            WHERE {sm_settle_remarks_col} <> 'CASH DISCOUNT'\n              AND {sm_settle_voucherdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){sm_settle_location_filter}\n            GROUP BY {sm_settle_salesmancode_col}\n        ) H ON S.{salesmancode_col} = H.SALESMANCODE" if salesmansettlement_table and sm_settle_salesmancode_col and sm_settle_voucherdate_col and sm_settle_voucheramount_col and sm_settle_remarks_col else ''
        query_parts.append('NVL(H.SHORT, 0) AS short' if short_join else '0 AS short')
        discount_join = f"\n        LEFT OUTER JOIN (\n            SELECT {sm_settle_salesmancode_col} AS SALESMANCODE,\n                   SUM({sm_settle_voucheramount_col}) AS DISCOUNT\n            FROM {salesmansettlement_table}\n            WHERE {sm_settle_remarks_col} = 'CASH DISCOUNT'\n              AND {sm_settle_voucherdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){sm_settle_location_filter}\n            GROUP BY {sm_settle_salesmancode_col}\n        ) Z ON S.{salesmancode_col} = Z.SALESMANCODE" if salesmansettlement_table and sm_settle_salesmancode_col and sm_settle_voucherdate_col and sm_settle_voucheramount_col and sm_settle_remarks_col else ''
        query_parts.append('NVL(Z.DISCOUNT, 0) AS discount' if discount_join else '0 AS discount')
        cash_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS CASH\n            FROM {billhdrhistory_table}\n            WHERE {history_billtype_col} = 'C'\n              AND {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD'){history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) E ON S.{salesmancode_col} = E.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(E.CASH, 0) AS cash' if cash_join else '0 AS cash')
        temp_join = f"\n        LEFT OUTER JOIN (\n            SELECT {history_salesmancode_col} AS SALESMANCODE,\n                   SUM({history_netbillamount_col}) AS TEMP\n            FROM {billhdrhistory_table}\n            WHERE {history_billdate_col} BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD') AND TO_DATE(:end_date, 'YYYY-MM-DD')\n              AND {history_netbillamount_col} > 0 AND {history_billtype_col} = 'T'{history_location_filter}\n            GROUP BY {history_salesmancode_col}\n        ) T ON S.{salesmancode_col} = T.SALESMANCODE" if billhdrhistory_table and history_salesmancode_col and history_billdate_col and history_netbillamount_col and history_billtype_col else ''
        query_parts.append('NVL(T.TEMP, 0) AS temp' if temp_join else '0 AS temp')
        closingcredit_join = f'\n        LEFT OUTER JOIN (\n            SELECT {salesmancode_col} AS SALESMANCODE,\n                   {closingcredit_col} AS CLOSINGCREDIT\n            FROM {salesman_table}{closingcredit_location_filter}\n        ) I ON S.{salesmancode_col} = I.SALESMANCODE' if closingcredit_col else ''
        query_parts.append(f'NVL(I.CLOSINGCREDIT, 0) AS closingcredit' if closingcredit_join else '0 AS closingcredit')
        query_parts.append('0 AS redemption')
        redemption_join = ''
        where_conditions = []
        params = {'location_code': location_code, 'start_date': start_date, 'end_date': end_date}
        if salesman_locationcode_col and location_code:
            where_conditions.append(f'S.{salesman_locationcode_col} = :location_code')
        if salesmancode:
            where_conditions.append(f'S.{salesmancode_col} = :salesmancode')
            params['salesmancode'] = salesmancode
        if salesmanname and salesmanname_col:
            where_conditions.append(f'S.{salesmanname_col} LIKE :salesmanname')
            params['salesmanname'] = f'%{salesmanname}%'
        where_clause = ' WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
        query = f"\n        SELECT {', '.join(query_parts)}\n        FROM {salesman_table} S\n        {opcredit_join}\n        {cashsales_join}\n        {cashgrv_join}\n        {creditsales_join}\n        {creditgrv_join}\n        {tmpcollection_join}\n        {collection_join}\n        {short_join}\n        {discount_join}\n        {cash_join}\n        {temp_join}\n        {closingcredit_join}\n        {redemption_join}{where_clause}\n        ORDER BY S.{salesmancode_col} ASC\n        "
        data = _process_salesman_summary_data(query, params, salesmanopening_table, opening_salesmancode_col, opening_billdate_col, opening_amount_col, opening_locationcode_col, start_date, salesmancode, salesmanname, salesmancode_col, salesmanname_col, return_json=False)
        filtered_data = [row for row in data if abs(float(row.get('calc_col14', 0) or 0)) > 0.01]
        pdf_data = _generate_salesman_summary_pdf(filtered_data, start_date, end_date, location_name)
        if not pdf_data:
            return Response('Failed to generate PDF', status=500, mimetype='text/plain')
        return Response(pdf_data, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename=salesman_summary_{start_date}_{end_date}.pdf'})
    except Exception as e:
        print(f'[ERROR generate_salesman_summary_report] {e}')
        import traceback
        traceback.print_exc()
        return Response(f'Error: {str(e)}', status=500, mimetype='text/plain')
