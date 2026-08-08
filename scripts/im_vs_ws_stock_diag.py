"""Compare ITEMMASTER stock vs WAREHOUSE_STOCK per item."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, '.env'))

from db import (
    WAREHOUSE_STOCK_TABLE,
    _detect_column,
    _detect_table,
    _get_table_columns,
    _iv_location_warehouse_stock_enabled,
    _safe_rows,
    _table_exists,
    is_location_warehouse_enabled,
    resolve_warehouse_master_table,
)
from db.itemmaster_core import _itemmaster_stock_qty_sql


def main():
    loc = int(os.getenv('IV_DIAG_LOCATION', '1'))
    tol = float(os.getenv('IV_DIAG_QTY_TOL', '0.0001'))

    print(f'=== ITEMMASTER vs WAREHOUSE_STOCK (location {loc}) ===\n')
    print(f'Warehouse stock enabled: {_iv_location_warehouse_stock_enabled(loc)}')
    print(f'Location warehouse flag: {is_location_warehouse_enabled(loc)}')

    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im_tbl:
        print('No ITEMMASTER.')
        return
    if not _table_exists(WAREHOUSE_STOCK_TABLE):
        print('No WAREHOUSE_STOCK table.')
        return

    im_cols = {str(c or '').upper() for c in (_get_table_columns(im_tbl) or [])}
    im_ic = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    im_lc = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    im_nm = _detect_column(im_tbl, ['ITEMNAME', 'ITEM_NAME', 'itemname'])
    cs_col = _detect_column(im_tbl, ['CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK'])
    branch_qty_sql = _itemmaster_stock_qty_sql(im_cols, 'im')

    store_cols = sorted(
        [c for c in im_cols if __import__('re').fullmatch(r'STORE\d+', c)],
        key=lambda x: int(x[5:]),
    )
    store_sum_sql = (
        '(' + ' + '.join(f'NVL(im.{c}, 0)' for c in store_cols) + ')'
        if store_cols else 'CAST(NULL AS NUMBER)'
    )

    loc_where = f' AND im.{im_lc} = :loc' if im_lc else ''
    name_sel = f'im.{im_nm}' if im_nm else "CAST(NULL AS VARCHAR2(200))"

    q = f'''
        SELECT im.{im_ic} AS itemcode,
               {name_sel} AS itemname,
               NVL(im.{cs_col}, 0) AS currentstock,
               ({branch_qty_sql}) AS branch_qty,
               {store_sum_sql} AS store_cols_sum,
               NVL(ws.ws_qty, 0) AS warehouse_stock_total,
               NVL(ws.wh_row_count, 0) AS wh_row_count
        FROM {im_tbl} im
        LEFT JOIN (
            SELECT ITEMCODE,
                   SUM(NVL(QTY, 0)) AS ws_qty,
                   COUNT(*) AS wh_row_count
            FROM {WAREHOUSE_STOCK_TABLE}
            WHERE LOCATIONCODE = :loc
            GROUP BY ITEMCODE
        ) ws ON ws.ITEMCODE = im.{im_ic}
        WHERE 1=1{loc_where}
          AND (
                ABS(NVL(im.{cs_col}, 0)) > :tol
             OR ABS(({branch_qty_sql})) > :tol
             OR ABS(NVL(ws.ws_qty, 0)) > :tol
          )
        ORDER BY ABS(NVL(ws.ws_qty, 0) - NVL(im.{cs_col}, 0)) DESC,
                 im.{im_ic}
    '''
    rows = _safe_rows(q, {'loc': loc, 'tol': tol}) or []

    mismatches = []
    im_only = []
    ws_only_qty = 0.0
    cs_only_qty = 0.0
    match_count = 0
    total_cs = 0.0
    total_ws = 0.0
    total_branch = 0.0

    all_items_q = f'''
        SELECT COUNT(*) AS cnt,
               NVL(SUM(NVL(im.{cs_col}, 0)), 0) AS sum_cs,
               NVL(SUM(({branch_qty_sql})), 0) AS sum_branch,
               NVL(SUM(NVL(ws.ws_qty, 0)), 0) AS sum_ws
        FROM {im_tbl} im
        LEFT JOIN (
            SELECT ITEMCODE, SUM(NVL(QTY, 0)) AS ws_qty
            FROM {WAREHOUSE_STOCK_TABLE}
            WHERE LOCATIONCODE = :loc
            GROUP BY ITEMCODE
        ) ws ON ws.ITEMCODE = im.{im_ic}
        WHERE 1=1{loc_where}
    '''
    totals = (_safe_rows(all_items_q, {'loc': loc}) or [{}])[0]
    total_cs = float(totals.get('sum_cs') or 0)
    total_branch = float(totals.get('sum_branch') or 0)
    total_ws = float(totals.get('sum_ws') or 0)
    item_count = int(totals.get('cnt') or 0)

    for r in rows:
        ic = int(r['itemcode'])
        cs = float(r.get('currentstock') or 0)
        bq = float(r.get('branch_qty') or 0)
        ws = float(r.get('warehouse_stock_total') or 0)
        store_sum = r.get('store_cols_sum')
        store_sum_f = float(store_sum) if store_sum is not None else None
        diff = round(ws - cs, 4)
        diff_branch = round(ws - bq, 4)

        if abs(diff) <= tol and abs(ws) <= tol and abs(cs) <= tol:
            continue
        if abs(diff) <= tol:
            match_count += 1
            continue

        row = {
            'itemcode': ic,
            'itemname': str(r.get('itemname') or '')[:40],
            'currentstock': cs,
            'branch_qty': bq,
            'store_sum': store_sum_f,
            'ws_qty': ws,
            'diff': diff,
            'wh_rows': int(r.get('wh_row_count') or 0),
        }
        mismatches.append(row)

        if abs(cs) > tol and abs(ws) <= tol:
            im_only.append(row)
            cs_only_qty += cs
        elif abs(ws) > tol and abs(cs) <= tol:
            ws_only_qty += ws

    # Items in WAREHOUSE_STOCK but not in ITEMMASTER for this location
    orphan_q = f'''
        SELECT ws.ITEMCODE AS itemcode,
               SUM(NVL(ws.QTY, 0)) AS ws_qty,
               COUNT(*) AS wh_row_count
        FROM {WAREHOUSE_STOCK_TABLE} ws
        WHERE ws.LOCATIONCODE = :loc
          AND NOT EXISTS (
              SELECT 1 FROM {im_tbl} im
              WHERE im.{im_ic} = ws.ITEMCODE
                {f' AND im.{im_lc} = :loc' if im_lc else ''}
          )
        GROUP BY ws.ITEMCODE
        HAVING ABS(SUM(NVL(ws.QTY, 0))) > :tol
        ORDER BY ABS(SUM(NVL(ws.QTY, 0))) DESC
    '''
    orphans = _safe_rows(orphan_q, {'loc': loc, 'tol': tol}) or []

    print('\n--- Branch totals ---')
    print(f'  Items in ITEMMASTER (location):     {item_count:,}')
    print(f'  SUM(CURRENTSTOCK):                  {total_cs:,.3f}')
    print(f'  SUM(branch_qty expression):         {total_branch:,.3f}')
    print(f'  SUM(WAREHOUSE_STOCK.QTY):           {total_ws:,.3f}')
    print(f'  Difference (WS - CURRENTSTOCK):     {total_ws - total_cs:,.3f}')
    print(f'  Difference (WS - branch_qty):       {total_ws - total_branch:,.3f}')

    if store_cols:
        print(f'  STORE columns used:                 {", ".join(store_cols)}')
        store_total = (_safe_rows(
            f'SELECT NVL(SUM({store_sum_sql.replace("im.", "im.")}), 0) AS v FROM {im_tbl} im WHERE 1=1{loc_where}',
            {'loc': loc},
        ) or [{}])[0]
        # fix query - store_sum_sql uses im alias
        st_q = f'SELECT NVL(SUM({store_sum_sql}), 0) AS v FROM {im_tbl} im WHERE 1=1{loc_where}'
        store_total_v = float((_safe_rows(st_q, {'loc': loc}) or [{}])[0].get('v') or 0)
        print(f'  SUM(STORE1+STORE2+...):             {store_total_v:,.3f}')
        print(f'  Difference (WS - STORE sum):        {total_ws - store_total_v:,.3f}')

    print('\n--- Mismatch summary ---')
    print(f'  Items with |WS - CURRENTSTOCK| > {tol}: {len(mismatches)}')
    print(f'  IM has stock, WS zero:              {len(im_only)} items  (CS qty sum {cs_only_qty:,.3f})')
    print(f'  WS has stock, IM CURRENTSTOCK zero: {sum(1 for m in mismatches if abs(m["currentstock"]) <= tol and abs(m["ws_qty"]) > tol)} items  (WS qty sum {ws_only_qty:,.3f})')
    print(f'  WS rows with no ITEMMASTER row:     {len(orphans)} items')

    if mismatches:
        print(f'\n--- All qty mismatches ({len(mismatches)} items) ---')
        hdr = f'{"Code":>8} {"CURRENTSTOCK":>14} {"BRANCH_QTY":>12} {"WS_TOTAL":>12} {"DIFF":>10} {"WH_ROWS":>7}  Name'
        print(hdr)
        for m in mismatches:
            print(
                f'{m["itemcode"]:>8} {m["currentstock"]:>14.3f} {m["branch_qty"]:>12.3f} '
                f'{m["ws_qty"]:>12.3f} {m["diff"]:>+10.3f} {m["wh_rows"]:>7}  {m["itemname"]}'
            )

        # Per-warehouse detail for top mismatches
        wm_tbl = resolve_warehouse_master_table()
        if wm_tbl and mismatches:
            top_ics = [m['itemcode'] for m in mismatches[:10]]
            bind = {'loc': loc}
            in_parts = []
            for i, ic in enumerate(top_ics):
                k = f'ic{i}'
                bind[k] = ic
                in_parts.append(f':{k}')
            detail_q = f'''
                SELECT ws.ITEMCODE AS itemcode,
                       TRIM(wm.WAREHOUSE_CODE) AS wh_code,
                       TRIM(wm.WAREHOUSE_NAME) AS wh_name,
                       NVL(ws.QTY, 0) AS qty
                FROM {WAREHOUSE_STOCK_TABLE} ws
                LEFT JOIN {wm_tbl} wm
                  ON wm.WAREHOUSE_ID = ws.WAREHOUSE_ID
                 AND wm.LOCATIONCODE = ws.LOCATIONCODE
                WHERE ws.LOCATIONCODE = :loc
                  AND ws.ITEMCODE IN ({", ".join(in_parts)})
                ORDER BY ws.ITEMCODE, UPPER(TRIM(wm.WAREHOUSE_CODE))
            '''
            details = _safe_rows(detail_q, bind) or []
            if details:
                print('\n--- Warehouse breakdown (top mismatch items) ---')
                cur_ic = None
                for d in details:
                    ic = int(d['itemcode'])
                    if ic != cur_ic:
                        cur_ic = ic
                        im_row = next((x for x in mismatches if x['itemcode'] == ic), {})
                        print(
                            f'\n  Item {ic}  CURRENTSTOCK={im_row.get("currentstock", 0):.3f}  '
                            f'WS total={im_row.get("ws_qty", 0):.3f}  diff={im_row.get("diff", 0):+.3f}'
                        )
                    print(
                        f'    {str(d.get("wh_code") or "?"):>8}  '
                        f'{str(d.get("wh_name") or "")[:30]:30}  qty={float(d.get("qty") or 0):.3f}'
                    )

    if orphans:
        print('\n--- WAREHOUSE_STOCK without ITEMMASTER row ---')
        for o in orphans[:20]:
            print(f'  Item {o["itemcode"]}: WS qty={float(o.get("ws_qty") or 0):.3f}  ({o.get("wh_row_count")} wh rows)')


if __name__ == '__main__':
    main()
