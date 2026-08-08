"""Sales Summary blueprint"""
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple
from nexa_http import Blueprint, redirect, render_template, request, session, url_for
from nexa_http import Response
from db import DATABASES, _detect_column, _fetch_rows, _get_connection, _get_scalar, _get_table_columns, set_active_db_key, set_active_db_host
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('sales_summary', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))

def _normalize_db_key(db_key: str) -> str:
    """Normalize db key values to known DATABASES keys."""
    if not db_key:
        return ''
    key = str(db_key).strip().upper()
    if key == 'TESTDB':
        return 'TESDB'
    return key

def _apply_active_connection(location_code: str) -> None:
    """Apply active database connection based on location_code"""
    normalized_code = _normalize_db_key(location_code)
    if normalized_code in DATABASES:
        db_config = DATABASES[normalized_code]
        print(f"[DEBUG _apply_active_connection] Connecting to {normalized_code}: {db_config['user']}@{db_config['dsn']}")
        set_active_db_key(normalized_code)
        set_active_db_host(None)
    else:
        set_active_db_key('HO')
        set_active_db_host(None)

def _detect_table(candidates: List[str]) -> str:
    """Return first table name that exists."""
    for table_name in candidates:
        try:
            if _get_table_columns(table_name):
                return table_name
        except Exception:
            continue
    return ''

def _fetch_summary_details(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """Fetch sales summary details based on the VB6 toplevelcategorydetails function."""
    billhdr_table = _detect_table(['BILLHDR', 'billhdr'])
    finalsale_table = _detect_table(['FINALSALE', 'finalsale'])
    drhdr_table = _detect_table(['DRHDR', 'drhdr'])
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    billdtl_table = _detect_table(['BILLDTL', 'billdtl'])
    itemmaster_table = _detect_table(['ITEMMASTER', 'itemmaster'])
    commission_table = _detect_table(['TBLCOMMISSIONREMOVEDCATEGORY', 'tblcommissionremovedcategory'])
    print(f'[DEBUG _fetch_summary_details] Tables detected:')
    print(f'  billhdr_table: {billhdr_table}')
    print(f'  finalsale_table: {finalsale_table}')
    print(f'  drhdr_table: {drhdr_table}')
    print(f'  customer_table: {customer_table}')
    print(f'  billdtl_table: {billdtl_table}')
    print(f'  itemmaster_table: {itemmaster_table}')
    print(f'  commission_table: {commission_table}')
    if not billhdr_table:
        print('[DEBUG _fetch_summary_details] BILLHDR table not found!')
        try:
            test_query = 'SELECT COUNT(*) AS cnt FROM BILLHDR WHERE ROWNUM <= 1'
            _, test_rows = _fetch_rows(test_query, {})
            print(f'[DEBUG _fetch_summary_details] Test query result: {test_rows}')
        except Exception as test_e:
            print(f'[DEBUG _fetch_summary_details] Test query failed: {test_e}')
        return []
    billdate_col = _detect_column(billhdr_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
    netbillamount_col = _detect_column(billhdr_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
    redemption_col = _detect_column(billhdr_table, ['REDEMPTIONAMOUNT', 'REDEMPTION', 'REDEMPTION_AMOUNT'])
    billno_col = _detect_column(billhdr_table, ['BILLNO', 'BILL_NO'])
    customercode_col = _detect_column(billhdr_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
    print(f'[DEBUG _fetch_summary_details] Columns detected for {billhdr_table}:')
    print(f'  billdate_col: {billdate_col}')
    print(f'  netbillamount_col: {netbillamount_col}')
    print(f'  redemption_col: {redemption_col}')
    print(f'  billno_col: {billno_col}')
    print(f'  customercode_col: {customercode_col}')
    if not billdate_col or not netbillamount_col or (not billno_col):
        print(f'[ERROR _fetch_summary_details] Required columns missing! billdate_col={billdate_col}, netbillamount_col={netbillamount_col}, billno_col={billno_col}')
        try:
            from db import _get_table_columns
            actual_cols = _get_table_columns(billhdr_table)
            print(f"[DEBUG _fetch_summary_details] Actual columns in {billhdr_table}: {(actual_cols[:10] if actual_cols else 'None')}")
        except Exception as e:
            print(f'[DEBUG _fetch_summary_details] Could not get table columns: {e}')
        return []
    transferbranch_col = None
    customercode_cust_col = None
    qty_col = None
    rate_col = None
    billno_dtl_col = None
    billno_hdr_col = None
    cost_col = None
    billdate_fs_col = None
    totaldiscount_col = None
    roundoff_col = None
    if finalsale_table:
        billdate_fs_col = _detect_column(finalsale_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
        totaldiscount_col = _detect_column(finalsale_table, ['TOTALDISCOUNT', 'TOTAL_DISCOUNT', 'DISCOUNT'])
        roundoff_col = _detect_column(finalsale_table, ['ROUNDOFF', 'ROUND_OFF', 'ROUND'])
    if customer_table:
        transferbranch_col = _detect_column(customer_table, ['TRANSFERBRANCH', 'TRANSFER_BRANCH', 'TRANSFER'])
        customercode_cust_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE', 'CODE'])
    if billdtl_table:
        qty_col = _detect_column(billdtl_table, ['QTY', 'QUANTITY', 'BILLQTY', 'BILL_QTY'])
        rate_col = _detect_column(billdtl_table, ['RATE', 'SELLRATE', 'PRICE', 'UNITPRICE'])
        billno_dtl_col = _detect_column(billdtl_table, ['BILLNO', 'BILL_NO'])
        billno_hdr_col = _detect_column(billhdr_table, ['BILLNO', 'BILL_NO'])
        cost_col = _detect_column(billdtl_table, ['COST', 'UNITCOST', 'COSTPRICE', 'UNIT_COST'])
    queries = []
    if redemption_col:
        queries.append(f"\n            SELECT 'SALES IN SYSTEM' AS description, \n                   SUM({netbillamount_col} + NVL({redemption_col}, 0)) AS amount\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    else:
        queries.append(f"\n            SELECT 'SALES IN SYSTEM' AS description, \n                   SUM({netbillamount_col}) AS amount\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    if finalsale_table and billdate_fs_col and totaldiscount_col:
        queries.append(f"\n            SELECT 'TOTAL DISCOUNT' AS description,\n                   COALESCE(SUM({totaldiscount_col}), 0) AS amount\n            FROM {finalsale_table}\n            WHERE TRUNC({billdate_fs_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_fs_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    if finalsale_table and billdate_fs_col and roundoff_col:
        queries.append(f"\n            SELECT 'TOTAL ROUND OFF' AS description,\n                   COALESCE(SUM({roundoff_col}), 0) AS amount\n            FROM {finalsale_table}\n            WHERE TRUNC({billdate_fs_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_fs_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    if redemption_col:
        queries.append(f"\n            SELECT 'REDEMPTION AMOUNT' AS description, \n                   NVL(SUM({redemption_col}), 0) AS amount\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    queries.append(f"\n        SELECT 'NUMBER OF INVOICES' AS description, \n               NVL(COUNT({billno_col}), 0) AS amount\n        FROM {billhdr_table}\n        WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n          AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n    ")
    if billdtl_table and cost_col and qty_col and rate_col and billno_dtl_col and billno_hdr_col and customercode_col and customercode_cust_col and transferbranch_col and customer_table:
        queries.append(f"\n                SELECT 'COST TO COST' AS description,\n                       NVL(SUM(DTL.{qty_col} * DTL.{rate_col}), 0) AS amount\n                FROM {billdtl_table} DTL\n                INNER JOIN {billhdr_table} HDR ON DTL.{billno_dtl_col} = HDR.{billno_hdr_col}\n                WHERE TRUNC(HDR.{billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n                  AND TRUNC(HDR.{billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n                  AND DTL.{rate_col} = DTL.{cost_col}\n                  AND NOT EXISTS (\n                      SELECT 1 FROM {customer_table} C \n                      WHERE C.{customercode_cust_col} = HDR.{customercode_col} \n                        AND C.{transferbranch_col} = 'Y'\n                  )\n            ")
    if billdtl_table and cost_col and qty_col and rate_col and billno_dtl_col and billno_hdr_col and customercode_col and customercode_cust_col and transferbranch_col and customer_table:
        queries.append(f"\n            SELECT 'BELOW COST' AS description,\n                   NVL(SUM(DTL.{qty_col} * (DTL.{rate_col} - DTL.{cost_col})) * -1, 0) AS amount\n            FROM {billdtl_table} DTL\n            INNER JOIN {billhdr_table} HDR ON DTL.{billno_dtl_col} = HDR.{billno_hdr_col}\n            WHERE DTL.{qty_col} > 0\n              AND TRUNC(HDR.{billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC(HDR.{billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n              AND DTL.{rate_col} < DTL.{cost_col}\n              AND NOT EXISTS (\n                  SELECT 1 FROM {customer_table} C \n                  WHERE C.{customercode_cust_col} = HDR.{customercode_col} \n                    AND C.{transferbranch_col} = 'Y'\n              )\n        ")
    if redemption_col:
        queries.append(f"\n            SELECT 'SALE RETURN' AS description,\n                   NVL(SUM({netbillamount_col} + NVL({redemption_col}, 0)), 0) AS amount\n            FROM {billhdr_table}\n            WHERE {netbillamount_col} < 0\n              AND TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    else:
        queries.append(f"\n            SELECT 'SALE RETURN' AS description,\n                   NVL(SUM({netbillamount_col}), 0) AS amount\n            FROM {billhdr_table}\n            WHERE {netbillamount_col} < 0\n              AND TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ")
    if not queries:
        print('[DEBUG _fetch_summary_details] No queries generated')
        return []
    combined_query = ' UNION ALL '.join(queries)
    print(f'[DEBUG _fetch_summary_details] Date range: {date_from} to {date_to}')
    print(f'[DEBUG _fetch_summary_details] Query count: {len(queries)}')
    print(f'[DEBUG _fetch_summary_details] Combined query (first 500 chars): {combined_query[:500]}')
    try:
        test_query = f"\n            SELECT COUNT(*) AS cnt\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        "
        _, test_rows = _fetch_rows(test_query, {'date_from': date_from, 'date_to': date_to})
        test_count = test_rows[0].get('cnt', 0) if test_rows else 0
        print(f'[DEBUG _fetch_summary_details] Test query - records in date range: {test_count}')
    except Exception as test_e:
        print(f'[ERROR _fetch_summary_details] Test query failed: {test_e}')
        import traceback
        traceback.print_exc()
    try:
        import time
        start_time = time.time()
        print(f'[DEBUG _fetch_summary_details] Executing combined UNION ALL query...')
        _, rows = _fetch_rows(combined_query, {'date_from': date_from, 'date_to': date_to})
        elapsed = time.time() - start_time
        print(f'[DEBUG _fetch_summary_details] Query executed in {elapsed:.2f} seconds')
        print(f'[DEBUG _fetch_summary_details] Rows returned: {(len(rows) if rows else 0)}')
        if rows:
            print(f'[DEBUG _fetch_summary_details] First 3 rows sample:')
            for i, row in enumerate(rows[:3]):
                print(f"  Row {i + 1}: description='{row.get('description')}', amount={row.get('amount')} (type: {type(row.get('amount'))})")
            return rows
        print(f'[DEBUG _fetch_summary_details] No rows returned from combined query')
        return []
    except Exception as e:
        print(f'[ERROR _fetch_summary_details] Combined query failed: {e}')
        import traceback
        traceback.print_exc()
        return []

def _fetch_daily_summary_details(date_from: str, date_to: str) -> Dict[str, Any]:
    """Fetch summary details broken down by day (for detailed view)."""
    start_date = datetime.strptime(date_from, '%Y-%m-%d')
    end_date = datetime.strptime(date_to, '%Y-%m-%d')
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    all_items = _fetch_summary_details(date_from, date_to)
    item_descriptions = [item.get('description', '') for item in all_items] if all_items else []
    daily_data = {}
    for date_str in dates:
        daily_items = _fetch_summary_details(date_str, date_str)
        daily_data[date_str] = {item.get('description', ''): float(item.get('amount', 0) or 0) for item in daily_items} if daily_items else {}
    return {'dates': dates, 'item_descriptions': item_descriptions, 'daily_data': daily_data}

def _fetch_daily_summary(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """Fetch daily summary for Excel export (Command1_Click equivalent)."""
    finalsale_table = _detect_table(['FINALSALE', 'finalsale'])
    drhdr_table = _detect_table(['DRHDR', 'drhdr'])
    if not finalsale_table:
        return []
    billdate_col = _detect_column(finalsale_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
    billdtlamount_col = _detect_column(finalsale_table, ['BILLDTLAMOUNT', 'BILL_DTL_AMOUNT', 'TOTALAMOUNT', 'TOTAL_AMOUNT'])
    totaldiscount_col = _detect_column(finalsale_table, ['TOTALDISCOUNT', 'TOTAL_DISCOUNT', 'DISCOUNT'])
    roundoff_col = _detect_column(finalsale_table, ['ROUNDOFF', 'ROUND_OFF', 'ROUND'])
    redemption_col = _detect_column(finalsale_table, ['REDEMPTION', 'REDEMPTIONAMOUNT', 'REDEMPTION_AMOUNT'])
    netbillamount_col = _detect_column(finalsale_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
    billdtlcost_col = _detect_column(finalsale_table, ['BILLDTLCOST', 'BILL_DTL_COST', 'TOTALCOST', 'TOTAL_COST'])
    if not billdate_col:
        return []
    drdate_col = _detect_column(drhdr_table, ['DRDATE', 'DR_DATE', 'DATE', 'DOCDATE']) if drhdr_table else None
    dramount_col = _detect_column(drhdr_table, ['DRAMOUNT', 'DR_AMOUNT', 'AMOUNT']) if drhdr_table else None
    select_parts = [f'f.{billdate_col} AS billdate']
    if billdtlamount_col:
        select_parts.append(f'NVL(f.{billdtlamount_col}, 0) AS billdtlamount')
    else:
        select_parts.append('0 AS billdtlamount')
    if totaldiscount_col:
        select_parts.append(f'NVL(f.{totaldiscount_col}, 0) AS totaldiscount')
    else:
        select_parts.append('0 AS totaldiscount')
    if roundoff_col:
        select_parts.append(f'NVL(f.{roundoff_col}, 0) AS roundoff')
    else:
        select_parts.append('0 AS roundoff')
    if redemption_col:
        select_parts.append(f'NVL(f.{redemption_col}, 0) AS redemption')
    else:
        select_parts.append('0 AS redemption')
    if netbillamount_col:
        select_parts.append(f'NVL(f.{netbillamount_col}, 0) AS netbillamount')
    else:
        select_parts.append('0 AS netbillamount')
    if drhdr_table and drdate_col and dramount_col:
        select_parts.append(f'NVL(d.dbnamount, 0) AS dbnamount')
        join_clause = f'\n            LEFT OUTER JOIN (\n                SELECT {drdate_col} AS drdate, SUM({dramount_col}) AS dbnamount\n                FROM {drhdr_table}\n                GROUP BY {drdate_col}\n            ) d ON f.{billdate_col} = d.drdate\n        '
    else:
        select_parts.append('0 AS dbnamount')
        join_clause = ''
    if billdtlcost_col:
        select_parts.append(f'NVL(f.{billdtlcost_col}, 0) AS billdtlcost')
    else:
        select_parts.append('0 AS billdtlcost')
    query = f"\n        SELECT {', '.join(select_parts)}\n        FROM {finalsale_table} f\n        {join_clause}\n        WHERE TRUNC(f.{billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n          AND TRUNC(f.{billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ORDER BY f.{billdate_col} ASC\n    "
    try:
        _, rows = _fetch_rows(query, {'date_from': date_from, 'date_to': date_to})
        return rows
    except Exception as e:
        print(f'[ERROR _fetch_daily_summary] {e}')
        import traceback
        traceback.print_exc()
        return []

def _calculate_totals(date_from: str, date_to: str) -> Dict[str, Any]:
    """Calculate total sale, deduction, net sale, target, percentage, and margin."""
    billhdr_table = _detect_table(['BILLHDR', 'billhdr'])
    finalsale_table = _detect_table(['FINALSALE', 'finalsale'])
    target_table = _detect_table(['TBLTARGETMONTHLY', 'tbltargetmonthly'])
    drhdr_table = _detect_table(['DRHDR', 'drhdr'])
    if not billhdr_table:
        return {}
    billdate_col = _detect_column(billhdr_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
    netbillamount_col = _detect_column(billhdr_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
    redemption_col = _detect_column(billhdr_table, ['REDEMPTIONAMOUNT', 'REDEMPTION', 'REDEMPTION_AMOUNT'])
    result = {}
    if redemption_col:
        query = f"\n            SELECT SUM({netbillamount_col} + NVL({redemption_col}, 0)) AS amount\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        "
    else:
        query = f"\n            SELECT SUM({netbillamount_col}) AS amount\n            FROM {billhdr_table}\n            WHERE TRUNC({billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n              AND TRUNC({billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        "
    try:
        total_sale = _get_scalar(query, {'date_from': date_from, 'date_to': date_to})
        result['total_sale'] = float(total_sale) if total_sale else 0.0
    except Exception:
        result['total_sale'] = 0.0
    result['deduction'] = 0.0
    result['net_sale'] = result['total_sale'] - result['deduction']
    try:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        year_col = _detect_column(target_table, ['YEAR', 'YR']) if target_table else None
        month_col = _detect_column(target_table, ['MONTH', 'MON']) if target_table else None
        amount_col = _detect_column(target_table, ['AMOUNT', 'TARGET', 'TARGETAMOUNT']) if target_table else None
        print(f'[DEBUG Target] Table: {target_table}, Year Col: {year_col}, Month Col: {month_col}, Amount Col: {amount_col}')
        print(f'[DEBUG Target] Date range: {date_from} to {date_to}')
        if target_table:
            try:
                test_query = f'SELECT COUNT(*) FROM {target_table}'
                test_count = _get_scalar(test_query, {})
                print(f'[DEBUG Target] Table {target_table} has {test_count} rows')
            except Exception as e:
                print(f'[DEBUG Target] Error querying table {target_table}: {e}')
        if target_table and year_col and month_col and amount_col:
            total_target = 0.0
            current_date = date_from_obj.replace(day=1)
            while current_date <= date_to_obj:
                year = current_date.year
                month_abbr = current_date.strftime('%b').upper()
                target = None
                month_formats = [month_abbr, str(current_date.month), str(current_date.month).zfill(2), current_date.strftime('%B').upper()]
                for month_val in month_formats:
                    try:
                        target_query = f'\n                            SELECT {amount_col} AS amount\n                            FROM {target_table}\n                            WHERE TO_CHAR({year_col}) = TO_CHAR(:year) AND UPPER(TO_CHAR({month_col})) = UPPER(:month)\n                        '
                        target = _get_scalar(target_query, {'year': year, 'month': str(month_val)})
                        if target:
                            total_target += float(target)
                            print(f'[DEBUG Target] Found target for {year}-{month_val}: {target}')
                            break
                    except Exception as e:
                        print(f'[DEBUG Target] Error trying month format {month_val}: {e}')
                        continue
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
            result['target'] = total_target
        else:
            result['target'] = 0.0
    except Exception as e:
        import traceback
        print(f'[DEBUG Target Calculation] Error: {e}')
        print(traceback.format_exc())
        result['target'] = 0.0
    if result['target'] > 0:
        result['percentage'] = result['net_sale'] / result['target'] * 100
    else:
        result['percentage'] = 0.0
    if finalsale_table:
        billdate_fs_col = _detect_column(finalsale_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
        netbillamount_fs_col = _detect_column(finalsale_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
        billdtlcost_fs_col = _detect_column(finalsale_table, ['BILLDTLCOST', 'BILL_DTL_COST', 'TOTALCOST', 'TOTAL_COST'])
        if billdate_fs_col and netbillamount_fs_col and billdtlcost_fs_col:
            margin_query = f"\n                SELECT ((SUM(f.{netbillamount_fs_col}) - SUM(f.{billdtlcost_fs_col})) / SUM(f.{netbillamount_fs_col})) * 100 AS margin\n                FROM {finalsale_table} f\n                WHERE TRUNC(f.{billdate_fs_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n                  AND TRUNC(f.{billdate_fs_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n                  AND f.{netbillamount_fs_col} > 0\n            "
            try:
                margin = _get_scalar(margin_query, {'date_from': date_from, 'date_to': date_to})
                result['margin'] = float(margin) if margin else 0.0
            except Exception:
                result['margin'] = 0.0
        else:
            result['margin'] = 0.0
    else:
        result['margin'] = 0.0
    return result

@bp.route('/sales-summary')
def sales_summary():
    print('[DEBUG sales_summary route] Route called!')
    if not session.get('user'):
        print('[DEBUG sales_summary route] No user in session, redirecting to login')
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    print(f'[DEBUG sales_summary route] user_dbkey: {user_dbkey}')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        print(f'[DEBUG sales_summary route] location_code: {location_code}')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    today = date.today().isoformat()
    date_from = request.args.get('date_from', '').strip() or today
    date_to = request.args.get('date_to', '').strip() or today
    print(f'[DEBUG sales_summary route] Date from: {date_from}, Date to: {date_to}')
    print(f'[DEBUG sales_summary route] ========================================')
    try:
        summary_details = _fetch_summary_details(date_from, date_to)
        print(f'[DEBUG sales_summary route] Summary details count: {(len(summary_details) if summary_details else 0)}')
        if summary_details is None:
            summary_details = []
        totals = _calculate_totals(date_from, date_to)
        print(f'[DEBUG sales_summary route] Totals: {totals}')
        print(f'[DEBUG sales_summary route] ========================================')
    except Exception as route_e:
        print(f'[ERROR sales_summary route] Exception in route: {route_e}')
        import traceback
        traceback.print_exc()
        summary_details = []
        totals = {'total_sale': 0.0, 'deduction': 0.0, 'net_sale': 0.0, 'target': 0.0, 'percentage': 0.0, 'margin': 0.0}
    if not totals:
        totals = {'total_sale': 0.0, 'deduction': 0.0, 'net_sale': 0.0, 'target': 0.0, 'percentage': 0.0, 'margin': 0.0}
    deduction = 0.0
    for row in summary_details:
        desc = str(row.get('description', '')).upper()
        if desc == 'COST TO COST':
            amount = float(row.get('amount', 0) or 0)
            deduction += amount
    totals['deduction'] = deduction
    totals['net_sale'] = totals.get('total_sale', 0.0) - deduction
    if totals.get('target', 0) > 0:
        totals['percentage'] = totals['net_sale'] / totals['target'] * 100
    else:
        totals['percentage'] = 0.0
    return render_template('sales_summary/sales_summary.html', summary_details=summary_details, totals=totals, date_from=date_from, date_to=date_to)

@bp.route('/sales-summary/detailed')
def sales_summary_detailed():
    """Show detailed day-by-day summary view."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    today = date.today().isoformat()
    date_from = request.args.get('date_from', '').strip() or today
    date_to = request.args.get('date_to', '').strip() or today
    try:
        daily_summary = _fetch_daily_summary_details(date_from, date_to)
    except Exception as e:
        print(f'[ERROR sales_summary_detailed] Exception: {e}')
        import traceback
        traceback.print_exc()
        daily_summary = {'dates': [], 'item_descriptions': [], 'daily_data': {}}
    return render_template('sales_summary/sales_summary_detailed.html', daily_summary=daily_summary, date_from=date_from, date_to=date_to)

def _get_transfer_sale_details(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """Get transfer sale details by customer (for details page when TRANSFER SALE is clicked)."""
    billhdr_table = _detect_table(['BILLHDR', 'billhdr'])
    customer_table = _detect_table(['CUSTOMER', 'CUSTOMERS', 'customers', 'customer'])
    if not billhdr_table or not customer_table:
        return []
    billdate_col = _detect_column(billhdr_table, ['BILLDATE', 'BILL_DATE', 'TRANDATE', 'TRANS_DATE'])
    netbillamount_col = _detect_column(billhdr_table, ['NETBILLAMOUNT', 'NETAMOUNT', 'NETTOTAL', 'NET_TOTAL'])
    billno_col = _detect_column(billhdr_table, ['BILLNO', 'BILL_NO'])
    customercode_col = _detect_column(billhdr_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTCODE', 'CUST_CODE'])
    customercode_cust_col = _detect_column(customer_table, ['CUSTOMERCODE', 'CUST_CODE', 'CUSTOMER_CODE', 'CODE'])
    customername_col = _detect_column(customer_table, ['CUSTOMERNAME', 'CUST_NAME', 'CUSTOMER_NAME', 'NAME'])
    transferbranch_col = _detect_column(customer_table, ['TRANSFERBRANCH', 'TRANSFER_BRANCH', 'TRANSFER'])
    if not all([billdate_col, netbillamount_col, billno_col, customercode_col, customercode_cust_col, transferbranch_col]):
        return []
    query = f"\n        SELECT \n            ROW_NUMBER() OVER (ORDER BY C.{customername_col}, H.{billdate_col}) AS slno,\n            H.{billno_col} AS billno,\n            H.{billdate_col} AS billdate,\n            H.{customercode_col} AS customercode,\n            C.{customername_col} AS customername,\n            NVL(H.{netbillamount_col}, 0) AS amount\n        FROM {billhdr_table} H\n        INNER JOIN {customer_table} C ON C.{customercode_cust_col} = H.{customercode_col}\n        WHERE C.{transferbranch_col} = 'Y'\n          AND TRUNC(H.{billdate_col}) >= TO_DATE(:date_from, 'YYYY-MM-DD')\n          AND TRUNC(H.{billdate_col}) <= TO_DATE(:date_to, 'YYYY-MM-DD')\n        ORDER BY C.{customername_col}, H.{billdate_col}\n    "
    try:
        _, rows = _fetch_rows(query, {'date_from': date_from, 'date_to': date_to})
        return rows
    except Exception as e:
        print(f'[ERROR _get_transfer_sale_details] {e}')
        import traceback
        traceback.print_exc()
        return []

@bp.route('/sales-summary/transfer-sale-details')
def transfer_sale_details():
    """Show transfer sale details by customer when TRANSFER SALE is clicked."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if not date_from or not date_to:
        return redirect(url_for('sales_summary.sales_summary'))
    rows = _get_transfer_sale_details(date_from, date_to)
    return render_template('sales_summary/transfer_sale_details.html', rows=rows, date_from=date_from, date_to=date_to)

@bp.route('/sales-summary/export')
def sales_summary_export():
    """Export daily summary to Excel (CSV format)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if not date_from or not date_to:
        return redirect(url_for('sales_summary.sales_summary'))
    daily_summary = _fetch_daily_summary(date_from, date_to)
    import csv
    import io
    from datetime import datetime
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['SLNO', 'BILL DATE', 'TOTAL AMOUNT', 'TOTAL DISCOUNT', 'TOTAL ROUNDOFF', 'TOTAL REDEMPTION', 'NET SALE', 'DEBIT NOTE', 'TOTAL COST'])
    for idx, row in enumerate(daily_summary, start=1):
        billdate = row.get('billdate')
        if billdate:
            if isinstance(billdate, datetime):
                billdate_str = billdate.strftime('%d/%b/%Y')
            else:
                billdate_str = str(billdate)
        else:
            billdate_str = ''
        writer.writerow([idx, billdate_str, f"{row.get('billdtlamount', 0):.2f}", f"{row.get('totaldiscount', 0):.2f}", f"{row.get('roundoff', 0):.2f}", f"{row.get('redemption', 0):.2f}", f"{row.get('netbillamount', 0):.2f}", f"{row.get('dbnamount', 0):.2f}", f"{row.get('billdtlcost', 0):.2f}"])
    output.seek(0)
    response = Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=sales_summary_{date_from}_to_{date_to}.csv'})
    return response

@bp.route('/sales-summary/export-details')
def sales_summary_export_details():
    """Export summary details to Excel (CSV format)."""
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    user_dbkey = session.get('tenant_id')
    if user_dbkey:
        _apply_active_connection(user_dbkey)
    else:
        location_code = session.get('location_code')
        if location_code:
            _apply_active_connection(location_code)
        elif session.get('user') == 'admin':
            _apply_active_connection('HO')
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if not date_from or not date_to:
        return redirect(url_for('sales_summary.sales_summary'))
    summary_details = _fetch_summary_details(date_from, date_to)
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Sl.No', 'Description', 'Value'])
    for idx, row in enumerate(summary_details, start=1):
        writer.writerow([idx, row.get('description', ''), f"{float(row.get('amount', 0) or 0):.2f}"])
    output.seek(0)
    response = Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=sales_summary_details_{date_from}_to_{date_to}.csv'})
    return response
