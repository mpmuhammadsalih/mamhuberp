"""Sales credit note — customer CRHDR/CRDTL + GL (financial adjustment, no stock)."""
from __future__ import annotations

import traceback
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    DEFAULT_PARTY_ACCOUNTS,
    _detect_column,
    _detect_table,
    _fetch_rows,
    _get_connection,
    ensure_gl_tables,
)


def _customer_gl_accounts(cur: Any, customer_code: int, loc_code: int) -> Dict[str, str]:
    defaults = {
        'receivable': str(DEFAULT_PARTY_ACCOUNTS.get('customer_receivable') or '1200').strip(),
        'sales': str(DEFAULT_PARTY_ACCOUNTS.get('customer_sales') or '4100').strip(),
    }
    cust_tbl = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERS', 'customers'])
    if not cust_tbl:
        return defaults
    code_col = _detect_column(cust_tbl, ['CUSTOMERCODE', 'customercode', 'CUST_CODE', 'CODE'])
    recv_col = _detect_column(cust_tbl, ['RECEIVABLEACCOUNT', 'receivableaccount'])
    sales_col = _detect_column(cust_tbl, ['SALESACCOUNT', 'salesaccount', 'SALES_ACCOUNT'])
    loc_col = _detect_column(cust_tbl, ['LOCATIONCODE', 'locationcode', 'LOCATION_CODE'])
    if not code_col:
        return defaults
    where = [f'{code_col} = :cc']
    params: Dict[str, Any] = {'cc': int(customer_code)}
    if loc_col:
        where.append(f'{loc_col} = :lc')
        params['lc'] = int(loc_code)
    sel = []
    if recv_col:
        sel.append(f'NVL({recv_col}, \'\') AS receivable')
    if sales_col:
        sel.append(f'NVL({sales_col}, \'\') AS sales')
    if not sel:
        return defaults
    try:
        cur.execute(
            f"SELECT {', '.join(sel)} FROM {cust_tbl} WHERE {' AND '.join(where)} AND ROWNUM = 1",
            params,
        )
        row = cur.fetchone()
        if not row:
            return defaults
        idx = 0
        out = dict(defaults)
        if recv_col:
            v = str(row[idx] or '').strip()
            if v and v != '0':
                out['receivable'] = v
            idx += 1
        if sales_col and idx < len(row):
            v = str(row[idx] or '').strip()
            if v and v != '0':
                out['sales'] = v
        return out
    except Exception:
        return defaults


def _ensure_credit_note_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'CRHDR'")
        if int(cur.fetchone()[0] or 0) == 0:
            cur.execute(
                """
                CREATE TABLE CRHDR (
                  LOCATIONCODE  NUMBER(2)      NOT NULL,
                  CRNO          NUMBER(10)     NOT NULL,
                  CRDATE        DATE,
                  CUSTOMERCODE  NUMBER(10),
                  CRAMOUNT      NUMBER(14,2),
                  REMARKS       VARCHAR2(200 BYTE),
                  CREATEDBY     VARCHAR2(20 BYTE)
                )
                """
            )
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'CRDTL'")
        if int(cur.fetchone()[0] or 0) == 0:
            cur.execute(
                """
                CREATE TABLE CRDTL (
                  LOCATIONCODE       NUMBER(2)          NOT NULL,
                  CRNO               NUMBER(10)         NOT NULL,
                  ITEMCODE           NUMBER(10)         NOT NULL,
                  UNITOFMEASUREMENT  VARCHAR2(10 BYTE)  NOT NULL,
                  QUANTITY           NUMBER(14,3),
                  OLDCOST            NUMBER(14,2),
                  NEWCOST            NUMBER(14,2),
                  VOUCHERAMOUNT      NUMBER(14,2)
                )
                """
            )


def ensure_credit_note_schema() -> None:
    with _get_connection() as conn:
        _ensure_credit_note_tables(conn)
        conn.commit()


def credit_note_next_no(loc_code: int) -> int:
    ensure_credit_note_schema()
    hdr = _detect_table(['CRHDR', 'crhdr'])
    if not hdr:
        return 1
    no_col = _detect_column(hdr, ['CRNO', 'crno'])
    loc_col = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    if not no_col:
        return 1
    where = ' 1=1 '
    params: Dict[str, Any] = {}
    if loc_col:
        where += f' AND {loc_col} = :loc'
        params['loc'] = int(loc_code)
    q = f'SELECT NVL(MAX({no_col}), 0) + 1 AS n FROM {hdr} WHERE {where}'
    try:
        _, rows = _fetch_rows(q, params)
        return int(rows[0]['n']) if rows else 1
    except Exception:
        return 1


def get_sales_credit_note_header(cr_no: int, loc_code: int) -> Optional[Dict[str, Any]]:
    ensure_credit_note_schema()
    hdr = _detect_table(['CRHDR', 'crhdr'])
    if not hdr:
        return None
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    h_no = _detect_column(hdr, ['CRNO', 'crno'])
    h_date = _detect_column(hdr, ['CRDATE', 'crdate'])
    h_cust = _detect_column(hdr, ['CUSTOMERCODE', 'customercode'])
    h_amt = _detect_column(hdr, ['CRAMOUNT', 'cramount'])
    h_rem = _detect_column(hdr, ['REMARKS', 'remarks'])
    h_created = _detect_column(hdr, ['CREATEDBY', 'createdby'])
    if not h_no:
        return None
    where = [f'h.{h_no} = :cr']
    params: Dict[str, Any] = {'cr': int(cr_no)}
    if h_loc:
        where.append(f'h.{h_loc} = :loc')
        params['loc'] = int(loc_code)
    cust_tbl = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERS'])
    cust_code = _detect_column(cust_tbl, ['CUSTOMERCODE', 'customercode']) if cust_tbl else None
    cust_name = _detect_column(cust_tbl, ['CUSTOMERNAME', 'customername', 'NAME']) if cust_tbl else None
    cols = [
        f'h.{h_no} AS crno',
        f'h.{h_date} AS crdate' if h_date else 'NULL AS crdate',
        f'h.{h_cust} AS customercode' if h_cust else 'NULL AS customercode',
        f'h.{h_amt} AS cramount' if h_amt else '0 AS cramount',
        f'h.{h_rem} AS remarks' if h_rem else "'' AS remarks",
        f'h.{h_created} AS createdby' if h_created else "'' AS createdby",
    ]
    join = ''
    if cust_tbl and cust_code and cust_name and h_cust:
        join = f' LEFT JOIN {cust_tbl} c ON c.{cust_code} = h.{h_cust} '
        cols.append(f'c.{cust_name} AS customername')
    q = f"SELECT {', '.join(cols)} FROM {hdr} h {join} WHERE {' AND '.join(where)}"
    try:
        _, rows = _fetch_rows(q, params)
        return rows[0] if rows else None
    except Exception:
        return None


def get_sales_credit_note_details(cr_no: int, loc_code: int) -> List[Dict[str, Any]]:
    ensure_credit_note_schema()
    dtl = _detect_table(['CRDTL', 'crdtl'])
    if not dtl:
        return []
    d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
    d_no = _detect_column(dtl, ['CRNO', 'crno'])
    d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
    d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'unitofmeasurement'])
    d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
    d_old = _detect_column(dtl, ['OLDCOST', 'oldcost'])
    d_new = _detect_column(dtl, ['NEWCOST', 'newcost'])
    d_voucher = _detect_column(dtl, ['VOUCHERAMOUNT', 'voucheramount'])
    if not all([d_no, d_item]):
        return []
    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    im_code = _detect_column(im_tbl, ['ITEMCODE', 'itemcode']) if im_tbl else None
    im_name = _detect_column(im_tbl, ['ITEMNAME', 'itemname', 'DESCRIPTION']) if im_tbl else None
    where = [f'd.{d_no} = :cr']
    params: Dict[str, Any] = {'cr': int(cr_no)}
    if d_loc:
        where.append(f'd.{d_loc} = :loc')
        params['loc'] = int(loc_code)
    cols = [
        f'd.{d_item} AS itemcode',
        f'd.{d_uom} AS uom' if d_uom else "'NOS' AS uom",
        f'NVL(d.{d_qty}, 0) AS quantity' if d_qty else '0 AS quantity',
        f'NVL(d.{d_old}, 0) AS rate' if d_old else '0 AS rate',
        f'NVL(d.{d_voucher}, 0) AS amount' if d_voucher else '0 AS amount',
    ]
    join = ''
    if im_tbl and im_code and im_name:
        join = f' LEFT JOIN {im_tbl} i ON i.{im_code} = d.{d_item} '
        cols.append(f'i.{im_name} AS itemname')
    q = f"SELECT {', '.join(cols)} FROM {dtl} d {join} WHERE {' AND '.join(where)} ORDER BY d.{d_item}"
    try:
        _, rows = _fetch_rows(q, params)
        return rows or []
    except Exception:
        return []


def get_sales_credit_note_list(loc_code: int) -> List[Dict[str, Any]]:
    ensure_credit_note_schema()
    hdr = _detect_table(['CRHDR', 'crhdr'])
    if not hdr:
        return []
    h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
    h_no = _detect_column(hdr, ['CRNO', 'crno'])
    h_date = _detect_column(hdr, ['CRDATE', 'crdate'])
    h_cust = _detect_column(hdr, ['CUSTOMERCODE', 'customercode'])
    h_amt = _detect_column(hdr, ['CRAMOUNT', 'cramount'])
    if not h_no:
        return []
    cust_tbl = _detect_table(['CUSTOMER', 'customer', 'CUSTOMERS'])
    cust_code = _detect_column(cust_tbl, ['CUSTOMERCODE', 'customercode']) if cust_tbl else None
    cust_name = _detect_column(cust_tbl, ['CUSTOMERNAME', 'customername', 'NAME']) if cust_tbl else None
    cols = [
        f'h.{h_no} AS crno',
        f'h.{h_date} AS crdate' if h_date else 'NULL AS crdate',
        f'h.{h_cust} AS customercode' if h_cust else 'NULL AS customercode',
        f'h.{h_amt} AS cramount' if h_amt else '0 AS cramount',
    ]
    join = ''
    if cust_tbl and cust_code and cust_name and h_cust:
        join = f' LEFT JOIN {cust_tbl} c ON c.{cust_code} = h.{h_cust} '
        cols.append(f'c.{cust_name} AS customername')
    where = ' 1=1 '
    params: Dict[str, Any] = {}
    if h_loc:
        where += f' AND h.{h_loc} = :loc'
        params['loc'] = int(loc_code)
    q = f"SELECT {', '.join(cols)} FROM {hdr} h {join} WHERE {where} ORDER BY h.{h_no} DESC"
    try:
        _, rows = _fetch_rows(q, params)
        return rows or []
    except Exception:
        return []


def save_sales_credit_note(
    *,
    loc_code: int,
    cr_no: int,
    cr_date: str,
    customer_code: int,
    cr_amount: float,
    remarks: str,
    lines: List[Dict[str, Any]],
    created_by: str = 'web',
) -> Optional[str]:
    with _get_connection() as conn:
        try:
            _ensure_credit_note_tables(conn)
            hdr = _detect_table(['CRHDR', 'crhdr'])
            dtl = _detect_table(['CRDTL', 'crdtl'])
            if not hdr or not dtl:
                raise ValueError('CRHDR/CRDTL tables not found')
            h_loc = _detect_column(hdr, ['LOCATIONCODE', 'locationcode'])
            h_no = _detect_column(hdr, ['CRNO', 'crno'])
            h_date = _detect_column(hdr, ['CRDATE', 'crdate'])
            h_cust = _detect_column(hdr, ['CUSTOMERCODE', 'customercode'])
            h_amt = _detect_column(hdr, ['CRAMOUNT', 'cramount'])
            h_remarks = _detect_column(hdr, ['REMARKS', 'remarks'])
            h_created = _detect_column(hdr, ['CREATEDBY', 'createdby'])
            if not all([h_loc, h_no]):
                raise ValueError('Required CRHDR columns not found')
            d_loc = _detect_column(dtl, ['LOCATIONCODE', 'locationcode'])
            d_no = _detect_column(dtl, ['CRNO', 'crno'])
            d_item = _detect_column(dtl, ['ITEMCODE', 'itemcode'])
            d_uom = _detect_column(dtl, ['UNITOFMEASUREMENT', 'unitofmeasurement'])
            d_qty = _detect_column(dtl, ['QUANTITY', 'quantity'])
            d_old = _detect_column(dtl, ['OLDCOST', 'oldcost'])
            d_new = _detect_column(dtl, ['NEWCOST', 'newcost'])
            d_voucher = _detect_column(dtl, ['VOUCHERAMOUNT', 'voucheramount'])
            if not all([d_loc, d_no, d_item, d_uom]):
                raise ValueError('Required CRDTL columns not found')
            try:
                date_fmt = datetime.strptime(cr_date[:10], '%Y-%m-%d').strftime('%d-%b-%Y').upper()
            except Exception:
                date_fmt = cr_date[:10]
            user = (created_by or 'web')[:20].replace("'", "''")
            remarks_txt = (remarks or '')[:200].replace("'", "''")
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {dtl} WHERE {d_loc} = :loc AND {d_no} = :cr', {'loc': loc_code, 'cr': cr_no})
                cur.execute(f'DELETE FROM {hdr} WHERE {h_loc} = :loc AND {h_no} = :cr', {'loc': loc_code, 'cr': cr_no})
                h_cols = [h_loc, h_no]
                h_vals = [str(loc_code), str(cr_no)]
                if h_date:
                    h_cols.append(h_date)
                    h_vals.append(f"TO_DATE('{date_fmt}', 'DD-MON-YYYY')")
                if h_cust:
                    h_cols.append(h_cust)
                    h_vals.append(str(int(customer_code or 0)))
                if h_amt:
                    h_cols.append(h_amt)
                    h_vals.append(str(round(float(cr_amount or 0), 2)))
                if h_remarks:
                    h_cols.append(h_remarks)
                    h_vals.append(f"'{remarks_txt}'")
                if h_created:
                    h_cols.append(h_created)
                    h_vals.append(f"'{user}'")
                cur.execute(f"INSERT INTO {hdr} ({', '.join(h_cols)}) VALUES ({', '.join(h_vals)})")
                merged: Dict[str, Dict[str, Any]] = {}
                line_total = 0.0
                for line in lines or []:
                    item = line.get('itemcode') or line.get('item_code')
                    if not item:
                        continue
                    uom_val = str(line.get('uom') or 'NOS').strip() or 'NOS'
                    key = f'{item}|{uom_val}'
                    qty = abs(float(line.get('quantity') or 0))
                    rate = float(line.get('rate') or 0)
                    amount = abs(float(line.get('amount') or qty * rate))
                    line_total += amount
                    base = merged.get(key)
                    if base is None:
                        merged[key] = {'item': item, 'uom': uom_val[:10], 'qty': qty, 'rate': rate, 'amount': amount}
                    else:
                        base['qty'] = float(base.get('qty') or 0) + qty
                        base['amount'] = float(base.get('amount') or 0) + amount
                        base['rate'] = rate
                if line_total > 1e-09 and abs(line_total - float(cr_amount or 0)) > 0.02:
                    cr_amount = line_total
                gl_accounts = _customer_gl_accounts(cur, int(customer_code), int(loc_code))
                sales_account = gl_accounts.get('sales') or '4100'
                recv_account = gl_accounts.get('receivable') or '1200'
                for _, ln in merged.items():
                    item = ln['item']
                    qty = float(ln.get('qty') or 0)
                    rate = float(ln.get('rate') or 0)
                    amount = float(ln.get('amount') or qty * rate)
                    uom = str(ln.get('uom') or 'NOS')[:10].replace("'", "''")
                    d_cols = [d_loc, d_no, d_item, d_uom]
                    d_vals = [str(loc_code), str(cr_no), str(item), f"'{uom}'"]
                    if d_qty:
                        d_cols.append(d_qty)
                        d_vals.append(str(qty))
                    if d_old:
                        d_cols.append(d_old)
                        d_vals.append(str(rate))
                    if d_new:
                        d_cols.append(d_new)
                        d_vals.append(str(rate))
                    if d_voucher:
                        d_cols.append(d_voucher)
                        d_vals.append(str(amount))
                    cur.execute(f"INSERT INTO {dtl} ({', '.join(d_cols)}) VALUES ({', '.join(d_vals)})")
                gl_total = round(float(cr_amount or line_total or 0), 2)
                if gl_total > 0.0005:
                    ensure_gl_tables()
                    gl_voucher_no = f'CN-{loc_code}-{cr_no}'[:30]
                    gl_ref_no = f'CN-{cr_no}'[:50]
                    gl_narration = f'Sales Credit Note {cr_no}'[:500]
                    gl_user = (created_by or 'web')[:50]
                    gl_party_type_col = _detect_column('GL_VOUCHER_DTL', ['PARTY_TYPE', 'party_type'])
                    gl_party_code_col = _detect_column('GL_VOUCHER_DTL', ['PARTY_CODE', 'party_code'])
                    cur.execute('DELETE FROM GL_VOUCHER_DTL WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
                    cur.execute('DELETE FROM GL_VOUCHER_HDR WHERE VOUCHER_NO = :vno', {'vno': gl_voucher_no})
                    cur.execute(
                        """
                        INSERT INTO GL_VOUCHER_HDR
                            (VOUCHER_NO, VOUCHER_DATE, REFERENCE_NO, NARRATION, SOURCE, CREATED_BY)
                        VALUES
                            (:vno, TO_DATE(:vdate, 'DD-MON-YYYY'), :ref, :nar, 'SALES_CREDIT_NOTE', :usr)
                        """,
                        {'vno': gl_voucher_no, 'vdate': date_fmt, 'ref': gl_ref_no, 'nar': gl_narration, 'usr': gl_user},
                    )
                    gl_line_no = 1
                    cur.execute('SELECT GL_VOUCHER_DTL_SEQ.NEXTVAL FROM DUAL')
                    gl_line_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO GL_VOUCHER_DTL
                            (LINE_ID, VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS)
                        VALUES
                            (:lid, :vno, :ln, :acc, :dr, 0, :rm)
                        """,
                        {
                            'lid': gl_line_id, 'vno': gl_voucher_no, 'ln': gl_line_no,
                            'acc': str(sales_account)[:20], 'dr': gl_total,
                            'rm': f'CN {cr_no} Sales reduction'[:250],
                        },
                    )
                    if gl_party_type_col and gl_party_code_col:
                        cur.execute(
                            'UPDATE GL_VOUCHER_DTL SET PARTY_TYPE = :pty, PARTY_CODE = :pcode WHERE LINE_ID = :lid',
                            {'pty': 'CUSTOMER', 'pcode': str(customer_code), 'lid': gl_line_id},
                        )
                    gl_line_no += 1
                    cur.execute('SELECT GL_VOUCHER_DTL_SEQ.NEXTVAL FROM DUAL')
                    gl_line_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO GL_VOUCHER_DTL
                            (LINE_ID, VOUCHER_NO, LINE_NO, ACCOUNT_CODE, DEBIT, CREDIT, REMARKS)
                        VALUES
                            (:lid, :vno, :ln, :acc, 0, :cr, :rm)
                        """,
                        {
                            'lid': gl_line_id, 'vno': gl_voucher_no, 'ln': gl_line_no,
                            'acc': str(recv_account)[:20], 'cr': gl_total,
                            'rm': f'CN {cr_no} Receivable credit'[:250],
                        },
                    )
                    if gl_party_type_col and gl_party_code_col:
                        cur.execute(
                            'UPDATE GL_VOUCHER_DTL SET PARTY_TYPE = :pty, PARTY_CODE = :pcode WHERE LINE_ID = :lid',
                            {'pty': 'CUSTOMER', 'pcode': str(customer_code), 'lid': gl_line_id},
                        )
            conn.commit()
        except ValueError as ve:
            try:
                conn.rollback()
            except Exception:
                pass
            return str(ve)
        except Exception as ex:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f'[ERROR save_sales_credit_note] cr_no={cr_no}: {ex}')
            traceback.print_exc()
            return str(ex) or 'Credit note save failed'
    return None
