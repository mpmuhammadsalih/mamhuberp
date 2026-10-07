def _bill_date_collection_value_to_iso(val: Any) -> Optional[str]:
    """Normalize bill date from grouped list rows to YYYY-MM-DD."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, str):
        vs = val.strip()
        if len(vs) >= 10 and vs[4] == '-':
            return vs[:10]
        try:
            return datetime.strptime(vs[:10], '%d/%m/%Y').strftime('%Y-%m-%d')
        except Exception:
            pass
    return None

def _online_rows_to_bulk_collection_items(invoices: List[Dict[str, Any]], salesman_code: str, transaction_iso_hint: str) -> List[Dict[str, Any]]:
    """Same eligibility rules as the collection screen Save (positive amount, skip over-collected rows)."""
    out: List[Dict[str, Any]] = []
    for item in invoices or []:
        try:
            coll = float(item.get('finalcollection') if item.get('finalcollection') is not None else item.get('collection') or 0)
        except (TypeError, ValueError):
            coll = 0.0
        try:
            balance = float(item.get('balance') or 0)
        except (TypeError, ValueError):
            balance = 0.0
        if coll > 0 and balance < coll:
            continue
        if coll <= 0:
            continue
        bid = str(item.get('id') or '').strip()
        bn = str(item.get('billno') or '').strip()
        cc = str(item.get('customercode') or '').strip()
        if not bid or not bn or (not cc):
            continue
        try:
            outst = float(item.get('outstanding') if item.get('outstanding') not in (None, '') else coll)
        except (TypeError, ValueError):
            outst = coll
        out.append({'invoice_no': bn, 'customer_code': cc, 'customer_name': item.get('customername') or '', 'amount': coll, 'id': bid, 'salesman_code': str(item.get('salesmancode') or salesman_code).strip(), 'bill_date': item.get('billdate'), 'bill_amount': outst})
    return out

def _temporary_collection_save_run(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Execute temporary-collection save POST payload; returns (body dict, HTTP status). No nonce rotation."""
    voucherno = data.get('voucherno', '').strip()
    transaction_date = data.get('transaction_date', '').strip()
    salesman_code = data.get('salesman_code', '').strip()
    remark = data.get('remark', 'Pending Amount').strip() or 'Pending Amount'
    collection_items = data.get('collection_items', [])
    generate_voucher_per_customer = data.get('generate_voucher_per_customer', False)
    if not transaction_date or not salesman_code:
        return ({'success': False, 'error': 'Date and salesman code are required'}, 400)
    if not collection_items:
        return ({'success': False, 'error': 'No collection items provided'}, 400)
    location_code = _resolve_location_code()
    current_user = session.get('user', '')
    try:
        settlement_table = _detect_table(['TBLSETTLEMENT', 'tblsettlement'])
        temp_settlement_table = _detect_table(['TBLTEMPSETTLEMENT', 'tbltempsettlement'])
        online_table = _detect_table(['ONLINE_TEMPORARY_COLLECTIONS', 'online_temporary_collections', 'ONLINETEMPORARYCOLLECTIONS'])
        if not settlement_table or not temp_settlement_table:
            return ({'success': False, 'error': 'Required tables not found'}, 500)
        try:
            if '/' in transaction_date:
                date_parts = transaction_date.split('/')
                if len(date_parts) == 3:
                    month = date_parts[1][:3].upper()
                    oracle_date = f'{date_parts[0]}/{month}/{date_parts[2]}'
                else:
                    oracle_date = transaction_date
            elif '-' in transaction_date:
                dt = datetime.strptime(transaction_date, '%Y-%m-%d')
                oracle_date = dt.strftime('%d/%b/%Y').upper()
            else:
                oracle_date = transaction_date
        except Exception as e:
            print(f'[DEBUG api_save] Date conversion error: {e}, using original: {transaction_date}')
            oracle_date = transaction_date
        customer_groups = defaultdict(list)
        customer_totals = defaultdict(float)
        invoice_data_map = {}
        invoice_numbers = []
        for item in collection_items:
            invoice_no = str(item.get('invoice_no', '')).strip()
            customer_code = str(item.get('customer_code', '')).strip()
            amount = float(item.get('amount', 0))
            if not invoice_no or not customer_code or amount <= 0:
                continue
            invoice_numbers.append(invoice_no)
            item_with_data = item.copy()
            customer_groups[customer_code].append(item_with_data)
            customer_totals[customer_code] += amount
        if invoice_numbers and settlement_table:
            with _get_connection() as check_conn:
                with check_conn.cursor() as check_cur:
                    check_billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
                    check_flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                    if check_billno_col and check_flag_col:
                        missing_invoices = []
                        for invoice_no in invoice_numbers:
                            try:
                                check_query = f"SELECT COUNT(*) FROM {settlement_table} WHERE {check_billno_col} = :billno AND {check_flag_col} = 'B'"
                                check_cur.execute(check_query, {'billno': invoice_no})
                                count = check_cur.fetchone()[0]
                                if count == 0:
                                    missing_invoices.append(invoice_no)
                            except Exception as e:
                                print(f'[DEBUG api_save] Error checking invoice {invoice_no}: {e}')
                                missing_invoices.append(invoice_no)
                        if missing_invoices:
                            missing_list = ', '.join(missing_invoices)
                            return ({'success': False, 'error': f"The following bill numbers are not found in TBLSETTLEMENT with FLAG='B'. Please make them temporary first: {missing_list}"}, 400)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                settlement_cols = _get_table_columns(settlement_table)
                locationcode_col = _detect_column(settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
                pendingno_col = _detect_column(settlement_table, ['PENDINGNO', 'PENDING_NO'])
                billno_col = _detect_column(settlement_table, ['BILLNO', 'BILL_NO'])
                billdate_col = _detect_column(settlement_table, ['BILLDATE', 'BILL_DATE'])
                billamount_col = _detect_column(settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT'])
                customercode_col = _detect_column(settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
                remark_col = _detect_column(settlement_table, ['REMARK', 'remark'])
                flag_col = _detect_column(settlement_table, ['FLAG', 'flag'])
                onlineflag_col = _detect_column(settlement_table, ['ONLINEFLAG', 'ONLINE_FLAG', 'onlineflag'])
                paidamount_col = _detect_column(settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                balance_col = _detect_column(settlement_table, ['BALANCE', 'balance'])
                paiddate_col = _detect_column(settlement_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                puser_col = _detect_column(settlement_table, ['PUSER', 'puser', 'P_USER'])
                voucherno_col = _detect_column(settlement_table, ['VOUCHERNO', 'VOUCHER_NO', 'voucherno'])
                status_col = _detect_column(settlement_table, ['STATUS', 'status'])
                pflag_col = _detect_column(settlement_table, ['PFLAG', 'P_FLAG', 'pflag'])
                settlement_salesmancode_col = _detect_column(settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by', 'CREATED_BY_USER', 'created_by_user'])
                sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                existing_settlement_cols_upper = [c.upper() for c in settlement_cols] if settlement_cols else []
                if not sett_createdby and 'CREATEDBY' not in existing_settlement_cols_upper:
                    try:
                        cur.execute(f'ALTER TABLE {settlement_table} ADD CREATEDBY VARCHAR2(50)')
                        sett_createdby = _detect_column(settlement_table, ['CREATEDBY', 'CREATED_BY', 'createdby', 'created_by'])
                    except Exception as e:
                        print(f'[DEBUG api_save] Error creating CREATEDBY column: {e}')
                if not sett_created_at and 'CREATED_AT' not in existing_settlement_cols_upper:
                    try:
                        cur.execute(f'ALTER TABLE {settlement_table} ADD CREATED_AT DATE')
                        import db as _db
                        if hasattr(_db, '_TABLE_COLUMNS_CACHE') and isinstance(getattr(_db, '_TABLE_COLUMNS_CACHE'), dict):
                            _db._TABLE_COLUMNS_CACHE.pop(settlement_table.upper(), None)
                        sett_created_at = _detect_column(settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                    except Exception as e:
                        print(f'[DEBUG api_save] Error creating CREATED_AT column: {e}')
                temp_locationcode_col = _detect_column(temp_settlement_table, ['LOCATIONCODE', 'LOCATION_CODE'])
                temp_pendingno_col = _detect_column(temp_settlement_table, ['PENDINGNO', 'PENDING_NO'])
                temp_customercode_col = _detect_column(temp_settlement_table, ['CUSTOMERCODE', 'CUSTOMER_CODE'])
                temp_status_col = _detect_column(temp_settlement_table, ['STATUS', 'status'])
                temp_paidamount_col = _detect_column(temp_settlement_table, ['PAIDAMOUNT', 'PAID_AMOUNT', 'paidamount'])
                temp_againstno_col = _detect_column(temp_settlement_table, ['AGAINSTNO', 'AGAINST_NO', 'againstno'])
                temp_paiddate_col = _detect_column(temp_settlement_table, ['PAIDDATE', 'PAID_DATE', 'paiddate'])
                temp_flag_col = _detect_column(temp_settlement_table, ['FLAG', 'flag'])
                temp_puser_col = _detect_column(temp_settlement_table, ['PUSER', 'puser', 'P_USER'])
                temp_remarks_col = _detect_column(temp_settlement_table, ['REMARKS', 'remarks', 'REMARK', 'remark'])
                temp_salesmancode_col = _detect_column(temp_settlement_table, ['SALESMANCODE', 'SALESMAN_CODE', 'salesmancode'])
                temp_billamount_col = _detect_column(temp_settlement_table, ['BILLAMOUNT', 'BILL_AMOUNT', 'billamount'])
                temp_version_col = _detect_column(temp_settlement_table, ['VERSION', 'version'])
                temp_created_at_col = _detect_column(temp_settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                temp_settlement_cols = _get_table_columns(temp_settlement_table)
                temp_settlement_cols_upper = [c.upper() for c in temp_settlement_cols] if temp_settlement_cols else []
                if not temp_created_at_col and 'CREATED_AT' not in temp_settlement_cols_upper:
                    try:
                        cur.execute(f'ALTER TABLE {temp_settlement_table} ADD CREATED_AT DATE')
                        import db as _db
                        if hasattr(_db, '_TABLE_COLUMNS_CACHE') and isinstance(getattr(_db, '_TABLE_COLUMNS_CACHE'), dict):
                            _db._TABLE_COLUMNS_CACHE.pop(temp_settlement_table.upper(), None)
                        temp_created_at_col = _detect_column(temp_settlement_table, ['CREATED_AT', 'CREATEDAT', 'created_at', 'createdat'])
                    except Exception as e:
                        print(f'[DEBUG api_save] Error creating CREATED_AT column in {temp_settlement_table}: {e}')
                online_status_col = None
                online_id_col = None
                online_billno_col = None
                online_customercode_col = None
                if online_table:
                    online_status_col = _detect_column(online_table, ['STATUS', 'status'])
                    online_id_col = _detect_column(online_table, ['ID', 'id'])
                    online_billno_col = _detect_column(online_table, ['BILLNO', 'BILL_NO', 'billno'])
                    online_customercode_col = _detect_column(online_table, ['CUSTOMERCODE', 'CUSTOMER_CODE', 'CUSTOMER', 'customer'])
                voucher_numbers = {}
                customer_index = 0
                for customer_code, customer_items in customer_groups.items():
                    customer_total = customer_totals[customer_code]
                    customer_index += 1
                    next_pending_int = _get_next_pendingno_inside_transaction(cur, settlement_table, temp_settlement_table, pendingno_col, temp_pendingno_col)
                    customer_voucherno = str(next_pending_int)
                    voucher_numbers[customer_code] = customer_voucherno
                    print(f'[DEBUG api_save] Customer {customer_index} ({customer_code}): pendingno {customer_voucherno}')
                    if all([locationcode_col, pendingno_col, billno_col, billdate_col, billamount_col, customercode_col, flag_col]):
                        insert_cols = [locationcode_col, pendingno_col, billno_col, billdate_col, billamount_col, customercode_col, flag_col]
                        insert_vals = [':location_code', ':pendingno', ':billno', f"TO_DATE(:billdate, 'DD/MON/YYYY')", ':billamount', ':customercode', "'R'"]
                        if voucherno_col and voucherno_col != pendingno_col:
                            insert_cols.append(voucherno_col)
                            insert_vals.append(':voucherno')
                        if settlement_salesmancode_col:
                            insert_cols.append(settlement_salesmancode_col)
                            insert_vals.append(':salesmancode')
                        if remark_col:
                            insert_cols.append(remark_col)
                            insert_vals.append(':remark')
                        if onlineflag_col:
                            insert_cols.append(onlineflag_col)
                            insert_vals.append("'O'")
                        if sett_createdby:
                            insert_cols.append(sett_createdby)
                            insert_vals.append(':createdby')
                        if sett_created_at:
                            insert_cols.append(sett_created_at)
                            insert_vals.append('SYSDATE')
                        insert_params = {'location_code': location_code, 'pendingno': customer_voucherno, 'billno': customer_voucherno, 'billdate': oracle_date, 'billamount': customer_total, 'customercode': customer_code, 'remark': remark}
                        if voucherno_col and voucherno_col != pendingno_col:
                            insert_params['voucherno'] = customer_voucherno
                        if settlement_salesmancode_col:
                            insert_params['salesmancode'] = salesman_code
                        if sett_createdby:
                            insert_params['createdby'] = current_user
                        insert_query = f"\n                            INSERT INTO {settlement_table} ({', '.join(insert_cols)})\n                            VALUES ({', '.join(insert_vals)})\n                        "
                        cur.execute(insert_query, insert_params)
                    for item in customer_items:
                        invoice_no = str(item.get('invoice_no', '')).strip()
                        amount = float(item.get('amount', 0))
                        item_id = str(item.get('id', '')).strip()
                        item_salesman_code = str(item.get('salesman_code', salesman_code)).strip()
                        if not invoice_no or amount <= 0:
                            continue
                        if all([temp_locationcode_col, temp_pendingno_col, temp_customercode_col, temp_status_col, temp_paidamount_col, temp_flag_col]):
                            temp_insert_cols = [temp_locationcode_col, temp_pendingno_col, temp_customercode_col, temp_status_col, temp_paidamount_col, temp_flag_col]
                            temp_insert_vals = [':location_code', ':pendingno', ':customercode', "'PAID'", ':paidamount', "'R'"]
                            if temp_againstno_col:
                                temp_insert_cols.append(temp_againstno_col)
                                temp_insert_vals.append(':againstno')
                            if temp_paiddate_col:
                                temp_insert_cols.append(temp_paiddate_col)
                                temp_insert_vals.append(f"TO_DATE(:paiddate, 'DD/MON/YYYY')")
                            if temp_puser_col:
                                temp_insert_cols.append(temp_puser_col)
                                temp_insert_vals.append(':puser')
                            if temp_remarks_col:
                                temp_insert_cols.append(temp_remarks_col)
                                temp_insert_vals.append(':remarks')
                            if temp_salesmancode_col:
                                temp_insert_cols.append(temp_salesmancode_col)
                                temp_insert_vals.append(':salesmancode')
                            if temp_billamount_col:
                                temp_insert_cols.append(temp_billamount_col)
                                temp_insert_vals.append('0')
                            if temp_version_col:
                                temp_insert_cols.append(temp_version_col)
                                temp_insert_vals.append('25')
                            if temp_created_at_col:
                                temp_insert_cols.append(temp_created_at_col)
                                temp_insert_vals.append('SYSDATE')
                            temp_insert_query = f"\n                                INSERT INTO {temp_settlement_table} ({', '.join(temp_insert_cols)})\n                                VALUES ({', '.join(temp_insert_vals)})\n                            "
                            temp_params = {'location_code': location_code, 'pendingno': customer_voucherno, 'customercode': customer_code, 'paidamount': amount, 'againstno': invoice_no, 'paiddate': oracle_date, 'puser': current_user, 'remarks': remark, 'salesmancode': item_salesman_code}
                            cur.execute(temp_insert_query, temp_params)
                        if paidamount_col and balance_col and billno_col and flag_col and customercode_col:
                            update_set = [f'{paidamount_col} = :paidamount', f'{balance_col} = ({balance_col} - :paidamount)']
                            update_params = {'paidamount': amount, 'billno': invoice_no, 'customercode': customer_code}
                            if paiddate_col:
                                update_set.append(f"{paiddate_col} = TO_DATE(:paiddate, 'DD/MON/YYYY')")
                                update_params['paiddate'] = oracle_date
                            if puser_col:
                                update_set.append(f'{puser_col} = :puser')
                                update_params['puser'] = current_user
                            if voucherno_col:
                                update_set.append(f'{voucherno_col} = :voucherno')
                                update_params['voucherno'] = customer_voucherno
                            if remark_col:
                                update_set.append(f'{remark_col} = :remark')
                                update_params['remark'] = remark
                            update_query = f"\n                                UPDATE {settlement_table}\n                                SET {', '.join(update_set)}\n                                WHERE {billno_col} = :billno\n                                  AND {flag_col} = 'B'\n                                  AND {customercode_col} = :customercode\n                            "
                            cur.execute(update_query, update_params)
                            if status_col and pflag_col and balance_col and voucherno_col:
                                status_update_query = f"\n                                    UPDATE {settlement_table}\n                                    SET {status_col} = 'PAID', {pflag_col} = 'Y'\n                                    WHERE {balance_col} = 0\n                                      AND {voucherno_col} = :voucherno\n                                      AND {billno_col} = :billno\n                                      AND {flag_col} = 'B'\n                                      AND {customercode_col} = :customercode\n                                "
                                cur.execute(status_update_query, {'voucherno': customer_voucherno, 'billno': invoice_no, 'customercode': customer_code})
                        if online_table and item_id and online_status_col and online_id_col and online_billno_col and online_customercode_col:
                            online_finalcollection_col = _detect_column(online_table, ['FINALCOLLECTION', 'FINAL_COLLECTION', 'finalcollection', 'final_collection'])
                            update_set = [f'{online_status_col} = 1']
                            update_params = {'billno': invoice_no, 'id': item_id, 'customercode': customer_code}
                            if online_finalcollection_col:
                                update_set.append(f'{online_finalcollection_col} = :finalcollection')
                                update_params['finalcollection'] = amount
                            online_update_query = f"\n                                UPDATE {online_table}\n                                SET {', '.join(update_set)}\n                                WHERE {online_billno_col} = :billno\n                                  AND {online_id_col} = :id\n                                  AND {online_customercode_col} = :customercode\n                            "
                            cur.execute(online_update_query, update_params)
                    conn.commit()
                    print(f'[DEBUG api_save] Committed customer {customer_index} ({customer_code})')
                print(f'[DEBUG api_save] All {customer_index} customer(s) saved')
                salesman_name = ''
                location_name = ''
                try:
                    salesman_info = _get_salesman_info(salesman_code)
                    if salesman_info:
                        salesman_name = (salesman_info.get('salesmanname') or '').strip()
                except Exception as e:
                    print(f'[DEBUG api_save] Error fetching salesman name: {e}')
                try:
                    loc_info = get_location_info_by_dbkey(None)
                    if loc_info:
                        location_name = (loc_info.get('locationname') or '').strip()
                except Exception as e:
                    print(f'[DEBUG api_save] Error fetching location name: {e}')
                pdf_data = None
                try:
                    pdf_data = _generate_collection_pdf(collection_items=collection_items, customer_groups=customer_groups, customer_totals=customer_totals, voucher_numbers=voucher_numbers, transaction_date=oracle_date, salesman_code=salesman_code, salesman_name=salesman_name, remark=remark, location_code=location_code, user_name=current_user, location_name=location_name, status_label='Completed')
                except Exception as e:
                    print(f'[ERROR api_save] PDF generation error: {e}')
                    import traceback
                    print(traceback.format_exc())
                response_data = {'success': True, 'message': 'Collection saved successfully'}
                if voucher_numbers:
                    response_data['voucher_numbers'] = voucher_numbers
                if pdf_data:
                    import base64
                    response_data['pdf_base64'] = base64.b64encode(pdf_data).decode('utf-8')
                    response_data['pdf_filename'] = f"collection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                return (response_data, 200)
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f'[ERROR _temporary_collection_save_run] {error_msg}')
        print(traceback.format_exc())
        return ({'success': False, 'error': f'Error saving collection: {error_msg}', 'error_type': type(e).__name__}, 500)
