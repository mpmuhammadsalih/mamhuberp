"""Compare Inventory Valuation total vs ITEMMASTER CURRENTSTOCK*AVERAGECOST."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, '.env'))

from db import (
    _detect_column,
    _detect_table,
    _get_table_columns,
    _iv_location_warehouse_stock_enabled,
    _iv_unit_cost_sql,
    _safe_rows,
    get_inventory_valuation_report,
    is_location_warehouse_enabled,
)
from db.itemmaster_core import _itemmaster_stock_qty_sql


def _sum_scalar(sql, params=None):
    rows = _safe_rows(sql, params or {}) or []
    if not rows:
        return 0.0
    v = list(rows[0].values())[0]
    return float(v or 0)


def main():
    loc = int(os.getenv('IV_DIAG_LOCATION', '1'))
    print(f'=== Inventory Valuation vs Item Master (location {loc}) ===\n')

    wh_enabled = _iv_location_warehouse_stock_enabled(loc)
    loc_wh = is_location_warehouse_enabled(loc)
    print(f'Warehouse stock enabled for branch: {wh_enabled} (location flag: {loc_wh})')

    # --- Inventory Valuation report (default filters) ---
    iv = get_inventory_valuation_report(
        loc,
        cost_method='average',
        include_zero=False,
        limit=500000,
        offset=0,
    )
    iv_zero = get_inventory_valuation_report(
        loc,
        cost_method='average',
        include_zero=True,
        limit=500000,
        offset=0,
    )
    s = iv.get('summary') or {}
    s0 = iv_zero.get('summary') or {}
    print(f'\nInventory Valuation (exclude zero): value={s.get("total_value"):,.2f}  qty={s.get("total_qty"):,.4f}  items={s.get("item_count")}')
    print(f'Inventory Valuation (include zero):   value={s0.get("total_value"):,.2f}  qty={s0.get("total_qty"):,.4f}  items={s0.get("item_count")}')

    im_tbl = _detect_table(['ITEMMASTER', 'itemmaster'])
    if not im_tbl:
        print('No ITEMMASTER table.')
        return
    im_cols = {str(c or '').upper() for c in (_get_table_columns(im_tbl) or [])}
    im_lc = _detect_column(im_tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    im_ic = _detect_column(im_tbl, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])

    cs = _detect_column(im_tbl, ['CURRENTSTOCK', 'CURRENT_STOCK', 'STOCK'])
    avg = _detect_column(im_tbl, ['AVERAGECOST', 'AVERAGE_COST', 'AVGCOST'])
    land = _detect_column(im_tbl, ['LANDINGCOST', 'LANDING_COST'])
    cost = _detect_column(im_tbl, ['COSTPRICE', 'COST_PRICE', 'COST'])

    branch_qty = _itemmaster_stock_qty_sql(im_cols, 'im')
    iv_cost = _iv_unit_cost_sql('im', im_cols, 'average')
    loc_clause = f' AND im.{im_lc} = :loc' if im_lc else ''

    # Pure CURRENTSTOCK * AVERAGECOST (what user asked)
    if cs and avg:
        pure = _sum_scalar(
            f'''SELECT NVL(SUM(NVL(im.{cs},0) * NVL(im.{avg},0)), 0) AS v
                FROM {im_tbl} im WHERE 1=1{loc_clause}
                  AND ABS(NVL(im.{cs},0)) > 0.0001''',
            {'loc': loc},
        )
        pure_all = _sum_scalar(
            f'''SELECT NVL(SUM(NVL(im.{cs},0) * NVL(im.{avg},0)), 0) AS v
                FROM {im_tbl} im WHERE 1=1{loc_clause}''',
            {'loc': loc},
        )
        print(f'\nITEMMASTER SUM(CURRENTSTOCK * AVERAGECOST) [qty>0 only]: {pure:,.2f}')
        print(f'ITEMMASTER SUM(CURRENTSTOCK * AVERAGECOST) [all items]:       {pure_all:,.2f}')

    # Branch qty SQL (what IV uses when warehouse stock off) * pure average
    if avg:
        branch_pure_avg = _sum_scalar(
            f'''SELECT NVL(SUM(({branch_qty}) * NVL(im.{avg},0)), 0) AS v
                FROM {im_tbl} im WHERE 1=1{loc_clause}
                  AND ABS({branch_qty}) > 0.0001''',
            {'loc': loc},
        )
        branch_iv_cost = _sum_scalar(
            f'''SELECT NVL(SUM(({branch_qty}) * ({iv_cost})), 0) AS v
                FROM {im_tbl} im WHERE 1=1{loc_clause}
                  AND ABS({branch_qty}) > 0.0001''',
            {'loc': loc},
        )
        print(f'\nITEMMASTER branch_qty * AVERAGECOST (qty>0):     {branch_pure_avg:,.2f}')
        print(f'ITEMMASTER branch_qty * IV cost chain (qty>0):   {branch_iv_cost:,.2f}')

    # WAREHOUSE_STOCK total
    ws_tbl = _detect_table(['WAREHOUSE_STOCK', 'warehouse_stock'])
    if ws_tbl and wh_enabled and avg:
        ws_val_pure_avg = _sum_scalar(
            f'''SELECT NVL(SUM(NVL(ws.QTY,0) * NVL(im.{avg},0)), 0) AS v
                FROM {ws_tbl} ws
                INNER JOIN {im_tbl} im ON im.{im_ic} = ws.ITEMCODE
                  {f' AND im.{im_lc} = ws.LOCATIONCODE' if im_lc else ''}
                WHERE ws.LOCATIONCODE = :loc
                  AND ABS(NVL(ws.QTY,0)) > 0.0001''',
            {'loc': loc},
        )
        ws_val_iv_cost = _sum_scalar(
            f'''SELECT NVL(SUM(NVL(ws.QTY,0) * ({iv_cost})), 0) AS v
                FROM {ws_tbl} ws
                INNER JOIN {im_tbl} im ON im.{im_ic} = ws.ITEMCODE
                  {f' AND im.{im_lc} = ws.LOCATIONCODE' if im_lc else ''}
                WHERE ws.LOCATIONCODE = :loc
                  AND ABS(NVL(ws.QTY,0)) > 0.0001''',
            {'loc': loc},
        )
        print(f'\nWAREHOUSE_STOCK qty * AVERAGECOST (qty>0):       {ws_val_pure_avg:,.2f}')
        print(f'WAREHOUSE_STOCK qty * IV cost chain (qty>0):     {ws_val_iv_cost:,.2f}')

    iv_val = float(s.get('total_value') or 0)
    ref = pure if cs and avg else branch_pure_avg
    diff = iv_val - ref
    print(f'\n--- Difference (IV exclude-zero vs CURRENTSTOCK*AVERAGECOST qty>0) ---')
    print(f'  IV value:     {iv_val:,.2f}')
    print(f'  IM ref value: {ref:,.2f}')
    print(f'  Difference:   {diff:,.2f}')

    # Breakdown buckets
    if cs and avg and im_ic and im_lc:
        rows = _safe_rows(
            f'''SELECT im.{im_ic} AS itemcode,
                       NVL(im.{cs},0) AS currentstock,
                       ({branch_qty}) AS branch_qty,
                       NVL(im.{avg},0) AS avgcost,
                       ({iv_cost}) AS iv_cost,
                       NVL(im.{land},0) AS landingcost,
                       NVL(im.{cost},0) AS costprice
                FROM {im_tbl} im
                WHERE im.{im_lc} = :loc
                  AND (ABS(NVL(im.{cs},0)) > 0.0001 OR ABS({branch_qty}) > 0.0001)''',
            {'loc': loc},
        ) or []

        ws_qty_by_item = {}
        if ws_tbl and wh_enabled:
            for r in _safe_rows(
                f'''SELECT ITEMCODE AS itemcode, SUM(NVL(QTY,0)) AS ws_qty
                    FROM {ws_tbl} WHERE LOCATIONCODE = :loc GROUP BY ITEMCODE''',
                {'loc': loc},
            ) or []:
                ws_qty_by_item[int(r['itemcode'])] = float(r.get('ws_qty') or 0)

        qty_mismatch_val = 0.0
        cost_fallback_val = 0.0
        im_only_val = 0.0
        ws_only_val = 0.0
        top_diffs = []

        for r in rows:
            ic = int(r['itemcode'])
            cs_q = float(r.get('currentstock') or 0)
            bq = float(r.get('branch_qty') or 0)
            ws_q = ws_qty_by_item.get(ic, 0.0) if wh_enabled else bq
            iv_q = ws_q if wh_enabled else bq
            avg_c = float(r.get('avgcost') or 0)
            iv_c = float(r.get('iv_cost') or 0)

            im_val = cs_q * avg_c
            iv_row_val = iv_q * iv_c
            pure_row = cs_q * avg_c

            if wh_enabled and abs(ws_q - cs_q) > 0.0001:
                qty_mismatch_val += (ws_q - cs_q) * avg_c

            if abs(iv_c - avg_c) > 0.0001 and abs(iv_q) > 0.0001:
                cost_fallback_val += iv_q * (iv_c - avg_c)

            if wh_enabled:
                if abs(cs_q) > 0.0001 and abs(ws_q) < 0.0001:
                    im_only_val += cs_q * avg_c
                if abs(ws_q) > 0.0001 and abs(cs_q) < 0.0001:
                    ws_only_val += ws_q * avg_c

            calc_iv = iv_q * avg_c  # IV qty but pure avg cost
            row_diff = iv_row_val - pure_row
            if abs(row_diff) > 0.01 or (wh_enabled and abs(ws_q - cs_q) > 0.0001):
                top_diffs.append({
                    'itemcode': ic,
                    'currentstock': cs_q,
                    'ws_qty': ws_q,
                    'branch_qty': bq,
                    'avgcost': avg_c,
                    'iv_cost': iv_c,
                    'diff': row_diff,
                    'qty_diff': ws_q - cs_q if wh_enabled else bq - cs_q,
                })

        top_diffs.sort(key=lambda x: abs(x['diff']), reverse=True)

        print(f'\n--- Breakdown of difference drivers (approximate) ---')
        if wh_enabled:
            print(f'  Qty mismatch (WS vs CURRENTSTOCK) × avgcost: {qty_mismatch_val:,.2f}')
            print(f'  Value on IM rows missing from WAREHOUSE_STOCK: {im_only_val:,.2f}')
            print(f'  Value on WS rows with zero CURRENTSTOCK:       {ws_only_val:,.2f}')
        print(f'  Cost fallback (landing/cost vs pure avgcost):  {cost_fallback_val:,.2f}')
        zero_excl = float(s0.get('total_value') or 0) - iv_val
        print(f'  Zero-qty exclusion effect (include - exclude): {zero_excl:,.2f}')

        print(f'\nTop 15 items by |value diff| (IV logic vs CURRENTSTOCK*AVGCOST):')
        print(f'{"Code":>8} {"CS":>10} {"WS":>10} {"AvgCost":>10} {"IVCost":>10} {"QtyDiff":>10} {"ValDiff":>12}')
        for t in top_diffs[:15]:
            print(
                f'{t["itemcode"]:>8} {t["currentstock"]:>10.3f} {t["ws_qty"]:>10.3f} '
                f'{t["avgcost"]:>10.4f} {t["iv_cost"]:>10.4f} {t["qty_diff"]:>10.3f} {t["diff"]:>12.2f}'
            )


if __name__ == '__main__':
    main()
