"""Temporary Pending blueprint - list, detail, update as temporary credit, print PDF, remove."""
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from nexa_http import Blueprint, jsonify, redirect, render_template, request, session, url_for
from db import _detect_column, _fetch_rows, _get_connection, get_location_info_by_dbkey
from addons.temporary_collection.controllers.routes import _bill_date_collection_value_to_iso, _detect_table, _generate_cash_receipt_pdf, _get_customer_name, _get_next_pendingno_inside_transaction, _get_salesman_info, _get_transaction_date, _resolve_location_code, REPORTLAB_AVAILABLE
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('temporary_pending', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
_ONLINE_TEMPORARY_AMOUNT_CANDIDATES = ('AMOUNT', 'amount', 'INVOICEAMOUNT', 'invoiceamount', 'NETBILLAMOUNT', 'netbillamount', 'NET_AMOUNT', 'net_amount', 'BILLAMOUNT', 'billamount', 'COLLECTION', 'collection', 'OUTSTANDING', 'outstanding')

def _sort_pdf_items_by_customer_and_add_totals(pdf_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort items by customername then billno; insert a subtotal row after each customer. Subtotal rows have is_subtotal=True."""
    if not pdf_items:
        return []
    sorted_items = sorted([i for i in pdf_items if not i.get('is_subtotal')], key=lambda x: ((x.get('customername') or '').strip().upper(), (x.get('customercode') or '').strip(), (x.get('billno') or '').strip()))
    result = []
    current_customer_key = None
    current_customer_name = ''
    customer_total = 0.0
    for item in sorted_items:
        amount = float(item.get('payamount') or item.get('amount') or 0)
        if amount <= 0:
            continue
        cust_name = (item.get('customername') or '').strip()
        cust_code = (item.get('customercode') or '').strip()
        key = (cust_name.upper(), cust_code)
        if current_customer_key is not None and key != current_customer_key:
            result.append({'billno': '', 'payamount': customer_total, 'amount': customer_total, 'billdate': '', 'customercode': '', 'customername': 'TOTAL', 'is_subtotal': True})
            customer_total = 0.0
        current_customer_key = key
        if cust_name:
            current_customer_name = cust_name
        customer_total += amount
        result.append(dict(item))
    if current_customer_key is not None and customer_total != 0:
        result.append({'billno': '', 'payamount': customer_total, 'amount': customer_total, 'billdate': '', 'customercode': '', 'customername': 'TOTAL', 'is_subtotal': True})
    return result

def _tp_parse_iso_date(s: Optional[str]) -> Optional[str]:
    """Return ``YYYY-MM-DD`` if valid, else None."""
    if not s:
        return None
    raw = str(s).strip()[:10]
    if len(raw) != 10:
        return None
    try:
        datetime.strptime(raw, '%Y-%m-%d')
        return raw
    except ValueError:
        return None

def _get_temporary_pending_list(date_from: Optional[str]=None, date_to: Optional[str]=None) -> List[Dict[str, Any]]:
    """Group by salesman + bill date from ONLINE_TEMPORARY (``h`` only for facts).
    Amount = SUM/COUNT over NVL(h.<amount_column>,0) detected on ONLINE_TEMPORARY; optional LEFT JOIN SALESMAN for names only.

    If ``date_from`` / ``date_to`` (ISO ``YYYY-MM-DD``) are provided, filter bill dates with that inclusive range
    and skip the default single-day transaction-date filter. Otherwise keep legacy behavior (transaction date only).
    """
    online_table = _detect_table(['ONLINE_TEMPORARY', 'online_temporary', 'ONLINETEMPORARY'])
    if not online_table:
        return []
    salesman_table = _detect_table(['SALESMAN', 'salesman', 'SALESMEN', 'salesmen'])
    location_code = _resolve_location_code()
    billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    salesman_code_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
    location_code_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
    status_col = _detect_column(online_table, ['STATUS', 'status'])
    amount_col = _detect_column(online_table, list(_ONLINE_TEMPORARY_AMOUNT_CANDIDATES))
    if not salesman_code_col:
        return []
    if not amount_col:
        amount_col = _detect_column(online_table, ['COLLECTION', 'collection', 'AMOUNT', 'amount'])
    sm_code_col = _detect_column(salesman_table, ['SALESMANCODE', 'salesmancode', 'CODE', 'code']) if salesman_table else None
    sm_name_col = _detect_column(salesman_table, ['SALESMANNAME', 'salesmanname', 'NAME', 'name']) if salesman_table else None
    sm_location_col = _detect_column(salesman_table, ['LOCATIONCODE', 'LOCATION_CODE', 'LOC_CODE', 'LOCCODE']) if salesman_table else None
    salesman_join = ''
    salesman_name_sql = 'NULL AS salesmanname'
    if salesman_table and sm_code_col and sm_name_col:
        salesman_join = f'LEFT JOIN {salesman_table} s ON h.{salesman_code_col} = s.{sm_code_col}'
        salesman_name_sql = f's.{sm_name_col} AS salesmanname'
        if sm_location_col:
            salesman_join += f' AND s.{sm_location_col} = {location_code}'
    where_clauses = []
    params = {}
    if location_code_col:
        where_clauses.append(f'h.{location_code_col} = :location_code')
        params['location_code'] = location_code
    df_iso = _tp_parse_iso_date(date_from)
    dt_iso = _tp_parse_iso_date(date_to)
    if df_iso and dt_iso and (df_iso > dt_iso):
        df_iso, dt_iso = (dt_iso, df_iso)
    transaction_date = _get_transaction_date(location_code)
    if billdate_col and (df_iso or dt_iso):
        if df_iso and dt_iso:
            where_clauses.append(f"TRUNC(h.{billdate_col}) BETWEEN TO_DATE(:tp_date_from, 'YYYY-MM-DD') AND TO_DATE(:tp_date_to, 'YYYY-MM-DD')")
            params['tp_date_from'] = df_iso
            params['tp_date_to'] = dt_iso
        elif df_iso:
            where_clauses.append(f"TRUNC(h.{billdate_col}) >= TO_DATE(:tp_date_from, 'YYYY-MM-DD')")
            params['tp_date_from'] = df_iso
        elif dt_iso:
            where_clauses.append(f"TRUNC(h.{billdate_col}) <= TO_DATE(:tp_date_to, 'YYYY-MM-DD')")
            params['tp_date_to'] = dt_iso
    elif transaction_date and billdate_col:
        try:
            if isinstance(transaction_date, str) and len(transaction_date) >= 10:
                date_str = transaction_date[:10]
                try:
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                    transaction_date_oracle = parsed_date.strftime('%d-%b-%Y').upper()
                    where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                    params['transaction_date'] = transaction_date_oracle
                except Exception as parse_err:
                    print(f'[DEBUG _get_temporary_pending_list] Date parse error: {parse_err}, using original format')
                    where_clauses.append(f"h.{billdate_col} = TO_DATE(:transaction_date, 'YYYY-MM-DD')")
                    params['transaction_date'] = transaction_date
        except Exception as e:
            print(f'[DEBUG _get_temporary_pending_list] Transaction date filter error: {e}')
    group_by_cols = [f'h.{salesman_code_col}', f'h.{billdate_col}']
    if salesman_table and sm_name_col:
        group_by_cols.append(f's.{sm_name_col}')
    if status_col and amount_col:
        invoicecount_sql = f'COUNT(*) AS invoicecount'
        totalamount_sql = f'SUM(NVL(h.{amount_col}, 0)) AS totalamount'
        min_status_sql = f'CASE WHEN COUNT(CASE WHEN h.{status_col} IN (0, 2) THEN 1 END) > 0 THEN 0 ELSE 1 END AS min_status'
    else:
        invoicecount_sql = f'COUNT(*) AS invoicecount' if status_col else 'COUNT(*) AS invoicecount'
        totalamount_sql = f'SUM(NVL(h.{amount_col}, 0)) AS totalamount' if amount_col else '0 AS totalamount'
        min_status_sql = f'MIN(h.{status_col}) AS min_status' if status_col else '0 AS min_status'
    query = f"\n        SELECT\n            h.{salesman_code_col} AS salesmancode,\n            {salesman_name_sql},\n            h.{billdate_col} AS billdate,\n            {invoicecount_sql},\n            {totalamount_sql},\n            {min_status_sql}\n        FROM {online_table} h\n        {salesman_join}\n        WHERE {(' AND '.join(where_clauses) if where_clauses else '1=1')}\n        GROUP BY {', '.join(group_by_cols)}\n        ORDER BY h.{billdate_col} DESC, h.{salesman_code_col}\n    "
    try:
        _, rows = _fetch_rows(query, params)
        return rows
    except Exception as e:
        print(f'[ERROR _get_temporary_pending_list] {e}')
        import traceback
        print(traceback.format_exc())
        return []

def _tp_detail_row_to_update_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Same field shape as temporary_pending_detail POST body (update-temporary)."""
    billno = str(item.get('billno') or '').strip()
    customercode = str(item.get('customercode') or '').strip()
    try:
        amount = float(item.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0.0
    bd = item.get('billdate')
    billdate_str = _bill_date_collection_value_to_iso(bd) or ''
    if not billdate_str and isinstance(bd, str) and (len(bd.strip()) >= 10):
        billdate_str = bd.strip()[:10]
    employeecode: Optional[int] = None
    ec = item.get('employeecode')
    if ec is not None and str(ec).strip() != '':
        try:
            employeecode = int(float(str(ec).strip()))
        except (ValueError, TypeError):
            employeecode = None
    ed = item.get('expecteddate')
    expecteddate: Optional[str] = None
    if ed is not None:
        if hasattr(ed, 'strftime'):
            expecteddate = ed.strftime('%Y-%m-%d')
        else:
            expecteddate = _bill_date_collection_value_to_iso(ed) or None
    remarks = item.get('remarks') or item.get('remark') or ''
    remarks = str(remarks).strip() if remarks else ''
    out: Dict[str, Any] = {'billno': billno, 'customercode': customercode, 'billdate': billdate_str, 'amount': amount, 'remarks': remarks or None}
    if employeecode is not None:
        out['employeecode'] = employeecode
    if expecteddate:
        out['expecteddate'] = expecteddate
    return out

def _temporary_pending_list_row_to_json(r: Dict[str, Any]) -> Dict[str, Any]:
    """Aligned with temporary_pending_list.html client rebuild."""
    sm = str(r.get('salesmancode') or '').strip()
    sn = str(r.get('salesmanname') or '').strip() or '-'
    bd = r.get('billdate')
    bill_iso = _bill_date_collection_value_to_iso(bd) or ''
    if isinstance(bd, datetime):
        bill_disp = bd.strftime('%d/%b/%Y').upper()
    elif isinstance(bd, str):
        bs = bd.strip()
        bill_disp = bs.upper() if bs else '-'
        if not bill_iso and len(bs) >= 10:
            bill_iso = _bill_date_collection_value_to_iso(bs) or bill_iso
    else:
        bill_disp = '-'
    try:
        ms = int(r.get('min_status') if r.get('min_status') is not None else 0)
    except (TypeError, ValueError):
        ms = 0
    try:
        invc = int(r.get('invoicecount') or 0)
    except (TypeError, ValueError):
        invc = 0
    try:
        tot = float(r.get('totalamount') if r.get('totalamount') is not None else 0)
    except (TypeError, ValueError):
        tot = 0.0
    return {'salesman_code': sm, 'salesman_name': sn, 'bill_date_iso': bill_iso, 'bill_date_display': bill_disp, 'invoicecount': invc, 'totalamount': round(tot, 2), 'min_status': ms}

def _get_temporary_pending_detail(salesman_code: str, billdate_param: Optional[str]=None, status_filter: Optional[List[int]]=None, include_completed: bool=False) -> List[Dict[str, Any]]:
    """Get detail rows from ONLINE_TEMPORARY. Default: pending only (status 0 or 2). If include_completed, do not filter by status (show completed lines too)."""
    online_table = _detect_table(['ONLINE_TEMPORARY', 'online_temporary', 'ONLINETEMPORARY'])
    if not online_table or not salesman_code:
        return []
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    employee_table = _detect_table(['EMPLOYEE1', 'employee1'])
    location_code = _resolve_location_code()
    billno_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
    billdate_col = _detect_column(online_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    customercode_col = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customer_code', 'customercode'])
    salesman_code_col = _detect_column(online_table, ['SALESMAN_CODE', 'SALESMANCODE', 'salesman_code', 'salesmancode'])
    location_code_col = _detect_column(online_table, ['LOCATION_CODE', 'LOCATIONCODE', 'location_code', 'locationcode'])
    status_col = _detect_column(online_table, ['STATUS', 'status'])
    amount_col = _detect_column(online_table, list(_ONLINE_TEMPORARY_AMOUNT_CANDIDATES))
    employee_code_col = _detect_column(online_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employee_code', 'employeecode'])
    expected_date_col = _detect_column(online_table, ['EXPECTEDDATE', 'EXPECTED_DATE', 'expecteddate', 'expected_date', 'EXPECTED', 'expected'])
    remarks_col = _detect_column(online_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
    if not salesman_code_col:
        return []
    if not billno_col:
        billno_col = _detect_column(online_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    if not billno_col or not customercode_col:
        return []
    if not amount_col:
        amount_col = _detect_column(online_table, ['COLLECTION', 'collection', 'AMOUNT', 'amount'])
    amount_sql = f'NVL(h.{amount_col}, 0) AS amount' if amount_col else '0 AS amount'
    customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE', 'code']) if customer_table else None
    customer_name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME', 'name']) if customer_table else None
    customer_location_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode', 'location_code']) if customer_table else None
    customer_join = ''
    customername_sql = 'NULL AS customername'
    if customer_table and customer_code_col and customer_name_col:
        customer_join = f'LEFT JOIN {customer_table} c ON h.{customercode_col} = c.{customer_code_col}'
        customername_sql = f'c.{customer_name_col} AS customername'
        if customer_location_col:
            customer_join += f' AND c.{customer_location_col} = {location_code}'
    emp_code_col = _detect_column(employee_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode']) if employee_table else None
    emp_name_col = _detect_column(employee_table, ['EMPLOYEENAME', 'EMPLOYEE_NAME', 'employeename']) if employee_table else None
    emp_location_col = _detect_column(employee_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) if employee_table else None
    employee_join = ''
    employee_code_sql = 'NULL AS employeecode'
    employee_name_sql = 'NULL AS employeename'
    if employee_table and employee_code_col and emp_code_col and emp_name_col:
        employee_join = f'LEFT JOIN {employee_table} e ON h.{employee_code_col} = e.{emp_code_col}'
        employee_code_sql = f'h.{employee_code_col} AS employeecode'
        employee_name_sql = f'e.{emp_name_col} AS employeename'
        if emp_location_col:
            employee_join += f' AND e.{emp_location_col} = {location_code}'
    expected_date_sql = 'NULL AS expecteddate'
    if expected_date_col:
        expected_date_sql = f'h.{expected_date_col} AS expecteddate'
    remarks_sql = 'NULL AS remarks'
    if remarks_col:
        remarks_sql = f'h.{remarks_col} AS remarks'
    where_clauses = [f'h.{salesman_code_col} = :salesman_code']
    params: Dict[str, Any] = {'salesman_code': salesman_code}
    if location_code_col:
        where_clauses.append(f'h.{location_code_col} = :location_code')
        params['location_code'] = location_code
    if status_col:
        if include_completed:
            pass
        elif status_filter is not None and len(status_filter) > 0:
            status_values = ', '.join((str(int(v)) for v in status_filter))
            where_clauses.append(f'h.{status_col} IN ({status_values})')
        else:
            where_clauses.append(f'h.{status_col} IN (0, 2)')
    if billdate_param and billdate_col:
        if len(billdate_param) == 10 and '-' in billdate_param:
            where_clauses.append(f"TRUNC(h.{billdate_col}) = TO_DATE(:billdate_param, 'YYYY-MM-DD')")
            params['billdate_param'] = billdate_param
        else:
            where_clauses.append(f"TRUNC(h.{billdate_col}) = TO_DATE(:billdate_param, 'DD-MON-YYYY')")
            params['billdate_param'] = billdate_param
    elif not billdate_param:
        transaction_date = _get_transaction_date(location_code)
        if transaction_date and billdate_col:
            try:
                if '/' in transaction_date:
                    date_parts = transaction_date.split('/')
                    if len(date_parts) == 3:
                        transaction_date_oracle = f'{date_parts[0]}-{date_parts[1][:3].upper()}-{date_parts[2]}'
                    else:
                        transaction_date_oracle = transaction_date.replace('/', '-')
                else:
                    transaction_date_oracle = transaction_date
                where_clauses.append(f"TRUNC(h.{billdate_col}) = TO_DATE(:transaction_date, 'DD-MON-YYYY')")
                params['transaction_date'] = transaction_date_oracle
            except Exception:
                pass
    query = f"\n        SELECT\n            h.{billno_col} AS billno,\n            h.{billdate_col} AS billdate,\n            h.{customercode_col} AS customercode,\n            {customername_sql},\n            {amount_sql},\n            {employee_code_sql},\n            {employee_name_sql},\n            {expected_date_sql},\n            {remarks_sql}\n        FROM {online_table} h\n        {customer_join}\n        {employee_join}\n        WHERE {' AND '.join(where_clauses)}\n        ORDER BY h.{billdate_col}, h.{billno_col}\n    "
    try:
        _, rows = _fetch_rows(query, params)
        if rows:
            return rows
    except Exception as e:
        print(f'[ERROR _get_temporary_pending_detail] table={online_table} {e}')
        import traceback
        print(traceback.format_exc())
    return []

@bp.route('/accounts/temporary-pending/api/list-rows', methods=['GET'])
def api_temporary_pending_list_rows():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    df = (request.args.get('date_from') or '').strip() or None
    dt = (request.args.get('date_to') or '').strip() or None
    plist = _get_temporary_pending_list(date_from=df, date_to=dt)
    rows = [_temporary_pending_list_row_to_json(r) for r in plist or []]
    return jsonify({'success': True, 'rows': rows})

@bp.route('/accounts/temporary-pending/api/group-items', methods=['GET'])
def api_temporary_pending_group_items():
    """Return detail lines formatted for POST update-temporary (bulk update from list)."""
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
    sm = (request.args.get('salesman_code') or '').strip()
    billdate = (request.args.get('billdate') or '').strip()
    if not sm:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    if len(billdate) < 10:
        return jsonify({'success': False, 'error': 'Bill date required'}, 400)
    try:
        datetime.strptime(billdate[:10], '%Y-%m-%d')
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid bill date'}, 400)
    rows = _get_temporary_pending_detail(sm, billdate[:10])
    items = [_tp_detail_row_to_update_item(r) for r in rows or []]
    items = [x for x in items if x.get('billno')]
    return jsonify({'success': True, 'salesman_code': sm, 'billdate': billdate[:10], 'items': items})

@bp.route('/accounts/temporary-pending')
def temporary_pending_list():
    """Temporary Pending List Page - from ONLINE_TEMPORARY (pending invoices)"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    df = (request.args.get('date_from') or '').strip() or None
    dt = (request.args.get('date_to') or '').strip() or None
    pending_list = _get_temporary_pending_list(date_from=df, date_to=dt)
    tpl_df = _tp_parse_iso_date(df) or ''
    tpl_dt = _tp_parse_iso_date(dt) or ''
    return render_template('temporary_pending/temporary_pending_list.html', pendings=pending_list, tpl_date_from=tpl_df, tpl_date_to=tpl_dt)

@bp.route('/accounts/temporary-pending/detail')
def temporary_pending_detail():
    """Temporary Pending Detail Page - invoice rows for selected salesman/date"""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    salesman_code = request.args.get('salesman_code', '').strip()
    billdate = request.args.get('billdate', '').strip()
    include_completed_raw = (request.args.get('include_completed') or '').strip().lower()
    include_completed = include_completed_raw in ('1', 'true', 'yes', 'on')
    details = _get_temporary_pending_detail(salesman_code, billdate if billdate else None, include_completed=include_completed)
    return render_template('temporary_pending/temporary_pending_detail.html', details=details, salesman_code=salesman_code, billdate=billdate, include_completed=include_completed)

@bp.route('/accounts/temporary-pending/update-temporary', methods=['POST'])
def api_update_temporary():
    """API: Update as Temporary Credit - update billhdr/billhdrhistory, insert tblsettlement/tbltempsettlement, set online_temporary status=1"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    try:
        loc_info = get_location_info_by_dbkey(None)
        expected_locationcode = loc_info.get('locationcode') if loc_info else None
    except Exception:
        expected_locationcode = None
    payload_location_code = data.get('location_code')
    if payload_location_code is not None and expected_locationcode is not None:
        try:
            payload_loc = int(payload_location_code) if str(payload_location_code).isdigit() else None
            if payload_loc is not None and payload_loc != int(expected_locationcode):
                return jsonify({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Location code mismatch. Do not save.'}, 400)
    items = data.get('items', [])
    salesman_code = (data.get('salesman_code') or '').strip()
    skip_pdf_flag = bool(data.get('skip_pdf'))
    if not items:
        return jsonify({'success': False, 'error': 'No items to update'}, 400)
    try:
        location_info = get_location_info_by_dbkey(None)
        location_code = location_info.get('locationcode')
        if location_code is None:
            location_code = 1
        location_code = int(location_code)
    except Exception as e:
        print(f'[DEBUG api_update_temporary] Could not get location: {e}')
        location_code = _resolve_location_code()
    current_user = session.get('user', '')
    billhdr_table = _detect_table(['BILLHDR', 'billhdr', 'BILL_HDR'])
    billhdrhistory_table = _detect_table(['BILLHDRHISTORY', 'billhdrhistory', 'BILL_HDR_HISTORY'])
    settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
    temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
    if not settlement_table or not temp_settlement_table:
        return jsonify({'success': False, 'error': 'Required tables (tblsettlement, tbltempsettlement) not found'}, 500)
    billhdr_billno = _detect_column(billhdr_table, ['BILLNO', 'BILL_NO', 'billno']) if billhdr_table else None
    billhdr_billtype = _detect_column(billhdr_table, ['BILLTYPE', 'BILL_TYPE', 'billtype']) if billhdr_table else None
    billhdr_billdate = _detect_column(billhdr_table, ['BILLDATE', 'BILL_DATE', 'billdate']) if billhdr_table else None
    billhdr_netamount = _detect_column(billhdr_table, ['NETBILLAMOUNT', 'NET_BILL_AMOUNT', 'netbillamount', 'BILLAMOUNT', 'billamount']) if billhdr_table else None
    billhdr_cust = _detect_column(billhdr_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode']) if billhdr_table else None
    billhdr_sm = _detect_column(billhdr_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode']) if billhdr_table else None
    hist_billno = _detect_column(billhdrhistory_table, ['BILLNO', 'BILL_NO', 'billno']) if billhdrhistory_table else None
    hist_billtype = _detect_column(billhdrhistory_table, ['BILLTYPE', 'BILL_TYPE', 'billtype']) if billhdrhistory_table else None
    hist_billdate = _detect_column(billhdrhistory_table, ['BILLDATE', 'BILL_DATE', 'billdate']) if billhdrhistory_table else None
    hist_netamount = _detect_column(billhdrhistory_table, ['NETBILLAMOUNT', 'NET_BILL_AMOUNT', 'netbillamount', 'BILLAMOUNT', 'billamount']) if billhdrhistory_table else None
    sett_loc = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
    sett_pending = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO'])
    sett_billno = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
    sett_billdate = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE'])
    sett_billamount = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT'])
    sett_cust = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
    sett_flag = _detect_column(settlement_table, ['FLAG', 'flag'])
    sett_status = _detect_column(settlement_table, ['STATUS', 'status'])
    sett_pflag = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
    sett_paidamount = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    sett_balance = _detect_column(settlement_table, ['BALANCE', 'balance'])
    sett_salesman = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    sett_employeecode = _detect_column(settlement_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
    sett_expecteddate = _detect_column(settlement_table, ['EXPECTEDDATE', 'EXPECTED_DATE', 'expecteddate', 'expected_date', 'EXPECTED', 'expected'])
    sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by', 'CREATED_BY_USER', 'created_by_user'])
    sett_remark = _detect_column(settlement_table, ['REMARKS', 'REMARK', 'remarks', 'remark'])
    sett_onlineflag = _detect_column(settlement_table, ['ONLINEFLAG', 'ONLINE_FLAG', 'ONLINEFLG', 'onlineflag'])
    sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
    temp_loc = _detect_column(temp_settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
    temp_pending = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO'])
    temp_billnumber = _detect_column(temp_settlement_table, ['BILLNUMBER', 'BILL_NUMBER', 'billnumber'])
    if not temp_billnumber:
        temp_billnumber = _detect_column(temp_settlement_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
    temp_billdate = _detect_column(temp_settlement_table, ['BILLDATE', 'BILL_DATE', 'billdate'])
    temp_billamount = _detect_column(temp_settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
    temp_cust = _detect_column(temp_settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
    temp_status = _detect_column(temp_settlement_table, ['STATUS', 'status'])
    temp_paidamount = _detect_column(temp_settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
    temp_flag = _detect_column(temp_settlement_table, ['FLAG', 'flag'])
    temp_puser = _detect_column(temp_settlement_table, ['PUSER', 'puser', 'P_USER'])
    temp_version = _detect_column(temp_settlement_table, ['VERSION', 'version'])
    temp_salesman = _detect_column(temp_settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
    temp_remark = _detect_column(temp_settlement_table, ['remarks'])
    if not all([sett_loc, sett_pending, sett_billno, sett_billdate, sett_billamount, sett_cust, sett_flag]):
        return jsonify({'success': False, 'error': 'tblsettlement columns not found'}, 500)
    if not all([temp_loc, temp_pending, temp_cust, temp_status, temp_paidamount, temp_flag]):
        return jsonify({'success': False, 'error': 'tbltempsettlement columns not found'}, 500)
    online_tables_to_update = []
    for ot in [['ONLINE_TEMPORARY', 'online_temporary', 'ONLINETEMPORARY']]:
        ot_table = _detect_table(ot)
        if not ot_table:
            continue
        ob = _detect_column(ot_table, ['BILLNO', 'BILL_NO', 'billno'])
        ol = _detect_column(ot_table, ['LOCATION_CODE', 'LOCATIONCODE', 'locationcode'])
        os_col = _detect_column(ot_table, ['STATUS', 'status'])
        if ob and ol and os_col:
            online_tables_to_update.append((ot_table, ob, ol, os_col))
    if not online_tables_to_update:
        return jsonify({'success': False, 'error': 'ONLINE_TEMPORARY is required to finish temporary credit (table not found or missing BILLNO / LOCATION / STATUS column). Settlement inserts were not performed.'}, 500)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if online_tables_to_update:
                    ot_table, ob, ol, os_col = online_tables_to_update[0]
                    billnos_to_check = [str(item.get('billno', '')).strip() for item in items if str(item.get('billno', '')).strip()]
                    if billnos_to_check:
                        placeholders = ', '.join([f':b{i}' for i in range(len(billnos_to_check))])
                        check_query = f'SELECT {ob} FROM {ot_table} WHERE {ob} IN ({placeholders}) AND {ol} = :loc'
                        check_params = {f'b{i}': b for i, b in enumerate(billnos_to_check)}
                        check_params['loc'] = location_code
                        cur.execute(check_query, check_params)
                        allowed_billnos = {str(row[0]).strip() for row in cur.fetchall()}
                        disallowed = [b for b in billnos_to_check if b not in allowed_billnos]
                        if disallowed:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            return jsonify({'success': False, 'error': f"Bill number(s) not found or not in current location: {', '.join(disallowed[:5])}{('...' if len(disallowed) > 5 else '')}"}, 400)
                next_pending_int = _get_next_pendingno_inside_transaction(cur, settlement_table, temp_settlement_table, sett_pending, temp_pending)
                try:
                    from db import _get_table_columns
                    existing_cols = _get_table_columns(settlement_table)
                    existing_cols_upper = [c.upper() for c in existing_cols]
                    if 'EMPLOYEECODE' not in existing_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD EMPLOYEECODE NUMBER(5)')
                            print(f'[DEBUG api_update_temporary] Created EMPLOYEECODE column in {settlement_table}')
                        except Exception as e:
                            print(f'[DEBUG api_update_temporary] Error creating EMPLOYEECODE column: {e}')
                    if 'EXPECTEDDATE' not in existing_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD EXPECTEDDATE DATE')
                            print(f'[DEBUG api_update_temporary] Created EXPECTEDDATE column in {settlement_table}')
                        except Exception as e:
                            print(f'[DEBUG api_update_temporary] Error creating EXPECTEDDATE column: {e}')
                    if 'CREATEDBY' not in existing_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD CREATEDBY VARCHAR2(50)')
                            print(f'[DEBUG api_update_temporary] Created CREATEDBY column in {settlement_table}')
                        except Exception as e:
                            print(f'[DEBUG api_update_temporary] Error creating CREATEDBY column: {e}')
                    if 'CREATED_AT' not in existing_cols_upper:
                        try:
                            cur.execute(f'ALTER TABLE {settlement_table} ADD CREATED_AT DATE')
                            print(f'[DEBUG api_update_temporary] Created CREATED_AT column in {settlement_table}')
                        except Exception as e:
                            print(f'[DEBUG api_update_temporary] Error creating CREATED_AT column: {e}')
                    sett_employeecode = _detect_column(settlement_table, ['EMPLOYEECODE', 'EMPLOYEE_CODE', 'employeecode'])
                    sett_expecteddate = _detect_column(settlement_table, ['EXPECTEDDATE', 'EXPECTED_DATE', 'expecteddate', 'expected_date', 'EXPECTED', 'expected'])
                    sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by', 'CREATED_BY_USER', 'created_by_user'])
                    sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                except Exception as e:
                    print(f'[DEBUG api_update_temporary] Error checking/creating columns: {e}')
                    import traceback
                    print(traceback.format_exc())
                for item in items:
                    billno = str(item.get('billno', '')).strip()
                    customercode = str(item.get('customercode', '')).strip()
                    amount = float(item.get('amount', 0))
                    billdate_str = item.get('billdate') or ''
                    employeecode = item.get('employeecode') or None
                    expecteddate = item.get('expecteddate') or None
                    remark = (item.get('remarks') or item.get('remark') or '').strip() or 'Temporary Credit'
                    print(f'[DEBUG api_update_temporary] Processing item - billno: {billno}, employeecode: {employeecode}, expecteddate: {expecteddate}, type: {type(expecteddate)}')
                    if not billno:
                        continue
                    current_pending = str(next_pending_int)
                    next_pending_int += 1
                    billdate_oracle = ''
                    netbillamount = amount
                    if billhdrhistory_table and hist_billno and hist_billdate and hist_netamount:
                        try:
                            q = f'SELECT {hist_billdate}, {hist_netamount} FROM {billhdrhistory_table} WHERE {hist_billno} = :b'
                            cur.execute(q, {'b': billno})
                            row = cur.fetchone()
                            if row:
                                billdate_oracle = row[0]
                                if billdate_oracle and hasattr(billdate_oracle, 'strftime'):
                                    billdate_oracle = billdate_oracle.strftime('%d/%b/%Y').upper()
                                netbillamount = float(row[1]) if row[1] is not None else amount
                        except Exception as e:
                            print(f'[DEBUG api_update_temporary] Error fetching from BILLHDRHISTORY: {e}')
                            pass
                    if not billdate_oracle and billdate_str:
                        try:
                            if len(billdate_str) == 10 and '-' in billdate_str:
                                from datetime import datetime as dt
                                d = dt.strptime(billdate_str, '%Y-%m-%d')
                                billdate_oracle = d.strftime('%d/%b/%Y').upper()
                            else:
                                billdate_oracle = billdate_str
                        except Exception:
                            billdate_oracle = billdate_str
                    if not billdate_oracle:
                        billdate_oracle = datetime.now().strftime('%d/%b/%Y').upper()
                    sm_code = salesman_code or str(item.get('salesmancode', '')).strip()
                    if settlement_table and sett_billno and sett_flag:
                        try:
                            check_query = f"SELECT COUNT(*) FROM {settlement_table} WHERE {sett_billno} = :billno AND {sett_flag} = 'B'"
                            cur.execute(check_query, {'billno': billno})
                            existing_count = cur.fetchone()[0]
                            if existing_count > 0:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                                return jsonify({'success': False, 'error': f"Bill number {billno} with flag='B' already exists in TBLSETTLEMENT. Please remove it first."}, 400)
                        except Exception as e:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            return jsonify({'success': False, 'error': f'Cannot verify/settle bill {billno}: {e!s}'}, 500)
                    sett_pairs = [(sett_loc, ':loc'), (sett_pending, ':pendingno'), (sett_billno, ':billno'), (sett_billdate, "TO_DATE(:billdate, 'DD/MON/YYYY')"), (sett_billamount, ':billamount'), (sett_cust, ':customercode'), (sett_flag, "'B'")]
                    if sett_salesman:
                        sett_pairs.append((sett_salesman, ':salesmancode'))
                    if sett_status:
                        sett_pairs.append((sett_status, "'PENDING'"))
                    if sett_pflag:
                        sett_pairs.append((sett_pflag, "'N'"))
                    if sett_paidamount:
                        sett_pairs.append((sett_paidamount, '0'))
                    if sett_balance:
                        sett_pairs.append((sett_balance, ':balance'))
                    expecteddate_oracle = None
                    if sett_employeecode:
                        sett_pairs.append((sett_employeecode, ':employeecode'))
                        print(f'[DEBUG api_update_temporary] Adding employeecode: {(employeecode if employeecode else 0)}')
                    if sett_expecteddate:
                        print(f'[DEBUG api_update_temporary] sett_expecteddate column exists: {sett_expecteddate}, expecteddate value: {expecteddate}, type: {type(expecteddate)}')
                        if expecteddate:
                            expecteddate_str = None
                            try:
                                if hasattr(expecteddate, 'strftime'):
                                    expecteddate_oracle = expecteddate.strftime('%d/%b/%Y').upper()
                                    print(f'[DEBUG api_update_temporary] Converted datetime object to: {expecteddate_oracle}')
                                elif isinstance(expecteddate, str):
                                    expecteddate_str = expecteddate.strip()
                                    if expecteddate_str and expecteddate_str.lower() not in ['none', 'null', '']:
                                        if len(expecteddate_str) >= 10 and expecteddate_str.count('-') >= 2:
                                            try:
                                                from datetime import datetime as dt
                                                if expecteddate_str[4] == '-' and expecteddate_str[7] == '-':
                                                    d = dt.strptime(expecteddate_str[:10], '%Y-%m-%d')
                                                    expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                                                    print(f'[DEBUG api_update_temporary] Converted YYYY-MM-DD to: {expecteddate_oracle}')
                                                else:
                                                    d = dt.strptime(expecteddate_str[:10], '%d-%m-%Y')
                                                    expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                                                    print(f'[DEBUG api_update_temporary] Converted DD-MM-YYYY to: {expecteddate_oracle}')
                                            except Exception as e:
                                                print(f'[DEBUG api_update_temporary] Error parsing date with dashes: {e}')
                                                expecteddate_oracle = None
                                        elif '/' in expecteddate_str:
                                            parts = expecteddate_str.split('/')
                                            if len(parts) == 3:
                                                if len(parts[1]) == 3 and parts[1].isalpha():
                                                    expecteddate_oracle = expecteddate_str.upper()
                                                    print(f'[DEBUG api_update_temporary] Using DD/MON/YYYY format: {expecteddate_oracle}')
                                                else:
                                                    try:
                                                        from datetime import datetime as dt
                                                        d = dt.strptime(expecteddate_str[:10], '%d/%m/%Y')
                                                        expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                                                        print(f'[DEBUG api_update_temporary] Converted DD/MM/YYYY to: {expecteddate_oracle}')
                                                    except Exception as e:
                                                        print(f'[DEBUG api_update_temporary] Error parsing DD/MM/YYYY: {e}')
                                                        expecteddate_oracle = None
                                            else:
                                                print(f'[DEBUG api_update_temporary] Invalid date format, parts count: {len(parts)}')
                                                expecteddate_oracle = None
                                        else:
                                            print(f"[DEBUG api_update_temporary] Date string doesn't match expected formats: {expecteddate_str}")
                                            expecteddate_oracle = None
                                else:
                                    expecteddate_str = str(expecteddate).strip()
                                    if expecteddate_str and expecteddate_str.lower() not in ['none', 'null', '']:
                                        if len(expecteddate_str) >= 10 and '-' in expecteddate_str:
                                            try:
                                                from datetime import datetime as dt
                                                if expecteddate_str[4] == '-' and expecteddate_str[7] == '-':
                                                    d = dt.strptime(expecteddate_str[:10], '%Y-%m-%d')
                                                    expecteddate_oracle = d.strftime('%d/%b/%Y').upper()
                                                    print(f'[DEBUG api_update_temporary] Converted from other type to: {expecteddate_oracle}')
                                            except Exception as e:
                                                print(f'[DEBUG api_update_temporary] Error converting from other type: {e}')
                                                expecteddate_oracle = None
                                if expecteddate_oracle and len(expecteddate_oracle) >= 9:
                                    sett_pairs.append((sett_expecteddate, "TO_DATE(:expecteddate, 'DD/MON/YYYY')"))
                                    print(f'[DEBUG api_update_temporary] Added expecteddate to INSERT: {expecteddate_oracle}')
                                else:
                                    print(f'[DEBUG api_update_temporary] Skipping expecteddate - invalid or empty: {expecteddate_oracle}')
                                    expecteddate_oracle = None
                            except Exception as e:
                                print(f'[DEBUG api_update_temporary] Error converting expecteddate: {e}, value: {expecteddate}, type: {type(expecteddate)}')
                                import traceback
                                print(traceback.format_exc())
                                expecteddate_oracle = None
                        else:
                            print(f'[DEBUG api_update_temporary] expecteddate is None or empty')
                    else:
                        print(f'[DEBUG api_update_temporary] sett_expecteddate column not found in table')
                    if sett_createdby:
                        sett_pairs.append((sett_createdby, ':createdby'))
                        print(f'[DEBUG api_update_temporary] Adding createdby: {current_user}')
                    if sett_remark:
                        sett_pairs.append((sett_remark, ':remark'))
                    if sett_onlineflag:
                        sett_pairs.append((sett_onlineflag, "'O'"))
                    if sett_created_at:
                        sett_pairs.append((sett_created_at, 'SYSDATE'))
                    sett_cols_clean = [c for c, _ in sett_pairs]
                    sett_vals_clean = [v for _, v in sett_pairs]
                    insert_sett = f"INSERT INTO {settlement_table} ({', '.join(sett_cols_clean)}) VALUES ({', '.join(sett_vals_clean)})"
                    sett_params = {'loc': location_code, 'pendingno': current_pending, 'billno': billno, 'billdate': billdate_oracle, 'billamount': int(netbillamount), 'customercode': customercode, 'balance': netbillamount}
                    if sett_salesman:
                        sett_params['salesmancode'] = sm_code
                    if sett_employeecode:
                        try:
                            if employeecode:
                                sett_params['employeecode'] = int(employeecode)
                            else:
                                sett_params['employeecode'] = 0
                        except (ValueError, TypeError):
                            sett_params['employeecode'] = 0
                    if sett_expecteddate and expecteddate_oracle:
                        sett_params['expecteddate'] = expecteddate_oracle
                    if sett_createdby:
                        sett_params['createdby'] = current_user
                    if sett_remark:
                        sett_params['remark'] = remark[:500] if remark else 'Temporary Credit'
                    cur.execute(insert_sett, sett_params)
                    temp_pairs = [(temp_loc, ':loc'), (temp_pending, ':pendingno'), (temp_billnumber or temp_pending, ':billno'), (temp_billdate, "TO_DATE(:billdate, 'DD/MON/YYYY')"), (temp_billamount, ':billamount'), (temp_cust, ':customercode'), (temp_status, "'PENDING'"), (temp_paidamount, '0'), (temp_flag, "'B'")]
                    if temp_salesman:
                        temp_pairs.append((temp_salesman, ':salesmancode'))
                    if temp_puser:
                        temp_pairs.append((temp_puser, ':puser'))
                    if temp_version:
                        temp_pairs.append((temp_version, '25'))
                    if temp_remark:
                        temp_pairs.append((temp_remark, ':remark'))
                    temp_cols_clean = [c for c, _ in temp_pairs]
                    temp_vals_clean = [v for _, v in temp_pairs]
                    insert_temp = f"INSERT INTO {temp_settlement_table} ({', '.join(temp_cols_clean)}) VALUES ({', '.join(temp_vals_clean)})"
                    temp_params = {'loc': location_code, 'pendingno': current_pending, 'billno': billno, 'billdate': billdate_oracle, 'billamount': int(netbillamount), 'customercode': customercode, 'puser': current_user}
                    if temp_remark:
                        temp_params['remark'] = remark[:500] if remark else 'Temporary Credit'
                    if temp_salesman:
                        temp_params['salesmancode'] = sm_code
                    cur.execute(insert_temp, temp_params)
                    if billhdr_table and billhdr_billno and billhdr_billtype:
                        try:
                            cur.execute(f"UPDATE {billhdr_table} SET {billhdr_billtype} = 'T' WHERE {billhdr_billno} = :b AND ({billhdr_billtype} = 'C' OR {billhdr_billtype} IS NULL)", {'b': billno})
                        except Exception as bh_err:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            return jsonify({'success': False, 'error': f'Update BILLHDR for bill {billno} failed (save aborted): {bh_err!s}'}, 500)
                    if billhdrhistory_table and hist_billno and hist_billtype:
                        try:
                            cur.execute(f"UPDATE {billhdrhistory_table} SET {hist_billtype} = 'T' WHERE {hist_billno} = :b AND ({hist_billtype} = 'C' OR {hist_billtype} IS NULL)", {'b': billno})
                        except Exception as hh_err:
                            try:
                                conn.rollback()
                            except Exception:
                                pass
                            return jsonify({'success': False, 'error': f'Update BILLHDRHISTORY for bill {billno} failed (save aborted): {hh_err!s}'}, 500)
                    for ot_table, ob, ol, os_col in online_tables_to_update:
                        cur.execute(f'UPDATE {ot_table} SET {os_col} = 1 WHERE {ob} = :b AND {ol} = :loc', {'b': billno, 'loc': location_code})
                try:
                    conn.commit()
                except Exception as commit_err:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise commit_err
        response_data = {'success': True}
        if skip_pdf_flag:
            return jsonify(response_data)
        try:
            salesman_name = ''
            location_name = ''
            try:
                salesman_info = _get_salesman_info(salesman_code)
                if salesman_info:
                    salesman_name = (salesman_info.get('salesmanname') or '').strip()
            except Exception as e:
                print(f'[DEBUG api_update_temporary] Error fetching salesman name: {e}')
            try:
                loc_info = get_location_info_by_dbkey(None)
                if loc_info:
                    location_name = (loc_info.get('locationname') or '').strip()
            except Exception as e:
                print(f'[DEBUG api_update_temporary] Error fetching location name: {e}')
            pdf_data = None
            try:
                voucherno = str(next_pending_int - 1) if next_pending_int > 1 else '1'
                pdf_items = []
                for item in items:
                    billno = str(item.get('billno', '')).strip()
                    amount = float(item.get('amount', 0))
                    billdate_str = item.get('billdate') or ''
                    customer_code = str(item.get('customercode', '')).strip()
                    customer_name = str(item.get('customername', '')).strip()
                    if customer_code and (not customer_name):
                        customer_name = _get_customer_name(customer_code)
                    pdf_items.append({'billno': billno, 'payamount': amount, 'amount': amount, 'billdate': billdate_str, 'customercode': customer_code, 'customername': customer_name})
                pdf_items = _sort_pdf_items_by_customer_and_add_totals(pdf_items)
                transaction_date = _get_transaction_date(location_code)
                pay_date = datetime.now()
                if transaction_date:
                    try:
                        pay_date = datetime.strptime(transaction_date[:10], '%Y-%m-%d')
                    except Exception:
                        pass
                pdf_data = _generate_cash_receipt_pdf(voucherno=f'TEMP-{voucherno}', customer_code='', customer_name='', items=pdf_items, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark='Temporary Credit', location_code=location_code, location_name=location_name, user_name=current_user, include_customer_in_header=False, include_customer_in_table=True, status_label='Completed', pdf_title='INVOICE PENDING', reduce_font=True, use_collection_summary_style=True)
                if pdf_data:
                    import base64
                    response_data['pdf_base64'] = base64.b64encode(pdf_data).decode('utf-8')
                    response_data['pdf_filename'] = f"temporary_collection_{salesman_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            except Exception as e:
                print(f'[ERROR api_update_temporary] PDF generation error: {e}')
                import traceback
                traceback.print_exc()
        except Exception as pdf_err:
            print(f'[ERROR api_update_temporary] PDF preparation error: {pdf_err}')
        return jsonify(response_data)
    except Exception as e:
        import traceback
        print(f'[ERROR api_update_temporary] {e}')
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-pending/print-pdf', methods=['GET'])
def api_print_temporary_pending_pdf():
    """API: Generate PDF receipt for completed temporary pending items"""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    salesman_code = request.args.get('salesman_code', '').strip()
    billdate = request.args.get('billdate', '').strip() or None
    status = (request.args.get('status', '') or '').strip().lower()
    if not salesman_code:
        return jsonify({'success': False, 'error': 'Salesman code required'}, 400)
    try:
        location_code = _resolve_location_code()
        pending_rows = _get_temporary_pending_detail(salesman_code, billdate if billdate else None, status_filter=[0])
        settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
        temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        if not pending_rows and (not settlement_table or not temp_settlement_table):
            return jsonify({'success': False, 'error': 'Required tables not found'}, 500)
        sett_pending = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO'])
        sett_billno = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
        sett_billdate = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE'])
        sett_billamount = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT'])
        sett_cust = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
        sett_flag = _detect_column(settlement_table, ['FLAG', 'flag'])
        sett_salesman = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
        sett_loc = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
        temp_pending = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO'])
        temp_flag = _detect_column(temp_settlement_table, ['FLAG', 'flag'])
        temp_loc = _detect_column(temp_settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
        if not pending_rows:
            if not all([sett_pending, sett_billno, sett_billdate, sett_billamount, sett_cust, temp_pending]):
                return jsonify({'success': False, 'error': 'Required columns not found'}, 500)
        customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
        customer_code_col = _detect_column(customer_table, ['CUST_CODE', 'CUSTOMERCODE', 'CUSTOMER_CODE', 'CODE']) if customer_table else None
        customer_name_col = _detect_column(customer_table, ['CUST_NAME', 'CUSTOMERNAME', 'CUSTOMER_NAME', 'NAME']) if customer_table else None
        customer_location_col = _detect_column(customer_table, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode', 'location_code']) if customer_table else None
        customer_join = ''
        customername_sql = 'NULL AS customername'
        if customer_table and customer_code_col and customer_name_col:
            customer_join = f'LEFT JOIN {customer_table} c ON s.{sett_cust} = c.{customer_code_col}'
            customername_sql = f'c.{customer_name_col} AS customername'
            if customer_location_col:
                customer_join += f' AND c.{customer_location_col} = {location_code}'
        completed_items = []
        if not pending_rows:
            where_clauses = []
            params = {}
            if temp_loc and sett_loc:
                where_clauses.append(f't.{temp_loc} = :location_code')
                where_clauses.append(f's.{sett_loc} = :location_code')
                params['location_code'] = location_code
            if sett_flag:
                where_clauses.append(f"s.{sett_flag} = 'B'")
            join_condition = f't.{temp_pending} = s.{sett_pending}'
            if sett_salesman:
                where_clauses.append(f's.{sett_salesman} = :salesman_code')
                params['salesman_code'] = salesman_code
            if billdate and sett_billdate:
                try:
                    if len(billdate) == 10 and '-' in billdate:
                        parsed_date = datetime.strptime(billdate, '%Y-%m-%d')
                        billdate_oracle = parsed_date.strftime('%d-%b-%Y').upper()
                        where_clauses.append(f"TRUNC(s.{sett_billdate}) = TO_DATE(:billdate, 'DD-MON-YYYY')")
                        params['billdate'] = billdate_oracle
                except Exception as e:
                    print(f'[DEBUG api_print_temporary_pending_pdf] Date conversion error: {e}')
            query = f"\n                SELECT DISTINCT\n                    s.{sett_billno} AS billno,\n                    s.{sett_billdate} AS billdate,\n                    s.{sett_billamount} AS billamount,\n                    s.{sett_cust} AS customercode,\n                    {customername_sql},\n                    t.{temp_pending} AS pendingno\n                FROM {temp_settlement_table} t\n                INNER JOIN {settlement_table} s ON {join_condition}\n                {customer_join}\n                WHERE {(' AND '.join(where_clauses) if where_clauses else '1=1')}\n                ORDER BY s.{sett_billno}\n            "
            try:
                print(f'[DEBUG api_print_temporary_pending_pdf] Query: {query[:300]}...')
                print(f'[DEBUG api_print_temporary_pending_pdf] Params: {params}')
                _, completed_items = _fetch_rows(query, params)
                print(f'[DEBUG api_print_temporary_pending_pdf] Found {len(completed_items)} completed items')
            except Exception as e:
                print(f'[ERROR api_print_temporary_pending_pdf] Query error: {e}')
                import traceback
                print(traceback.format_exc())
                return jsonify({'success': False, 'error': 'Failed to fetch completed items'}, 500)
            if not completed_items:
                return jsonify({'success': False, 'error': 'No completed records found'}, 404)
        salesman_name = ''
        location_name = ''
        try:
            salesman_info = _get_salesman_info(salesman_code)
            if salesman_info:
                salesman_name = (salesman_info.get('salesmanname') or '').strip()
        except Exception as e:
            print(f'[DEBUG api_print_temporary_pending_pdf] Error fetching salesman name: {e}')
        try:
            loc_info = get_location_info_by_dbkey(None)
            if loc_info:
                location_name = (loc_info.get('locationname') or '').strip()
        except Exception as e:
            print(f'[DEBUG api_print_temporary_pending_pdf] Error fetching location name: {e}')
        source_items = pending_rows if pending_rows else completed_items
        pdf_items = []
        for item in source_items:
            billno = str(item.get('billno') or '').strip()
            amount = float(item.get('billamount') or item.get('amount') or 0)
            billdate_raw = item.get('billdate')
            billdate_str = ''
            if billdate_raw:
                if hasattr(billdate_raw, 'strftime'):
                    billdate_str = billdate_raw.strftime('%Y-%m-%d')
                elif isinstance(billdate_raw, str):
                    billdate_str = billdate_raw[:10] if len(billdate_raw) >= 10 else billdate_raw
            customer_code = str(item.get('customercode') or '').strip()
            customer_name = str(item.get('customername') or '').strip()
            if customer_code and (not customer_name):
                customer_name = _get_customer_name(customer_code)
            pdf_items.append({'billno': billno, 'payamount': amount, 'amount': amount, 'billdate': billdate_str, 'customercode': customer_code, 'customername': customer_name})
        pdf_items = _sort_pdf_items_by_customer_and_add_totals(pdf_items)
        transaction_date = _get_transaction_date(location_code)
        pay_date = datetime.now()
        if transaction_date:
            try:
                pay_date = datetime.strptime(transaction_date[:10], '%Y-%m-%d')
            except Exception:
                pass
        if not pdf_items or len(pdf_items) == 0:
            return jsonify({'success': False, 'error': 'No items found for PDF generation'}, 400)
        status_label = 'Pending' if pending_rows else 'Completed'
        pdf_data = None
        pdf_error = None
        try:
            if not REPORTLAB_AVAILABLE:
                pdf_error = 'PDF library (reportlab) is not available. Please install reportlab package.'
            else:
                pdf_data = _generate_cash_receipt_pdf(voucherno=f'TEMP-{salesman_code}', customer_code='', customer_name='Temporary Collection', items=pdf_items, pay_date=pay_date, salesman_code=salesman_code, salesman_name=salesman_name, remark='Temporary Credit', location_code=location_code, location_name=location_name, user_name=session.get('user', ''), include_customer_in_header=False, include_customer_in_table=True, status_label=status_label, pdf_title='INVOICE PENDING', reduce_font=True, use_collection_summary_style=True)
                if not pdf_data:
                    pdf_error = 'PDF generation returned empty data'
        except Exception as pdf_gen_err:
            pdf_error = f'PDF generation error: {str(pdf_gen_err)}'
            print(f'[ERROR api_print_temporary_pending_pdf] {pdf_error}')
            import traceback
            print(traceback.format_exc())
        if pdf_data:
            try:
                import base64
                response_data = {'success': True, 'pdf_base64': base64.b64encode(pdf_data).decode('utf-8'), 'pdf_filename': f"temporary_collection_{salesman_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
                return jsonify(response_data)
            except Exception as encode_err:
                print(f'[ERROR api_print_temporary_pending_pdf] Base64 encoding error: {encode_err}')
                return jsonify({'success': False, 'error': f'Failed to encode PDF: {str(encode_err)}'}, 500)
        else:
            error_msg = pdf_error or 'Failed to generate PDF. Please check server logs for details.'
            return jsonify({'success': False, 'error': error_msg}, 500)
    except Exception as e:
        import traceback
        print(f'[ERROR api_print_temporary_pending_pdf] Error: {e}')
        return jsonify({'success': False, 'error': str(e)}, 500)

@bp.route('/accounts/temporary-pending/remove', methods=['POST'])
def api_remove_temporary_pending():
    """API: Mark one record as removed (status=2) in ONLINE_TEMPORARY."""
    if not session.get('user'):
        return jsonify({'error': 'Not authenticated'}, 401)
    data = request.get_json(silent=True) or {}
    billno = str(data.get('billno', '')).strip()
    customercode = str(data.get('customercode', '')).strip()
    if not billno:
        return jsonify({'success': False, 'error': 'Bill no required'}, 400)
    location_code = _resolve_location_code()
    removed = False
    tbl = _detect_table(['ONLINE_TEMPORARY', 'online_temporary', 'ONLINETEMPORARY'])
    if tbl:
        billno_col = _detect_column(tbl, ['BILLNO', 'BILL_NO', 'billno'])
        loc_col = _detect_column(tbl, ['LOCATION_CODE', 'LOCATIONCODE', 'locationcode'])
        cust_col = _detect_column(tbl, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'customercode'])
        status_col = _detect_column(tbl, ['STATUS', 'status'])
        if billno_col and loc_col:
            try:
                with _get_connection() as conn:
                    with conn.cursor() as cur:
                        if status_col:
                            if cust_col:
                                cur.execute(f'UPDATE {tbl} SET {status_col} = 2 WHERE {billno_col} = :b AND {loc_col} = :loc AND {cust_col} = :c', {'b': billno, 'loc': location_code, 'c': customercode})
                            else:
                                cur.execute(f'UPDATE {tbl} SET {status_col} = 2 WHERE {billno_col} = :b AND {loc_col} = :loc', {'b': billno, 'loc': location_code})
                        elif cust_col:
                            cur.execute(f'DELETE FROM {tbl} WHERE {billno_col} = :b AND {loc_col} = :loc AND {cust_col} = :c', {'b': billno, 'loc': location_code, 'c': customercode})
                        else:
                            cur.execute(f'DELETE FROM {tbl} WHERE {billno_col} = :b AND {loc_col} = :loc', {'b': billno, 'loc': location_code})
                        if cur.rowcount and cur.rowcount > 0:
                            removed = True
                    conn.commit()
            except Exception as e:
                print(f'[ERROR api_remove_temporary_pending] {tbl}: {e}')
    return jsonify({'success': True, 'removed': removed})
