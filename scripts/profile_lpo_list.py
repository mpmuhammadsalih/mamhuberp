"""Profile LPO list query timings."""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

from flask import Flask

app = Flask(__name__)
with app.app_context():
    from addons.purchase.controllers import routes as pr
    from db import _fetch_rows

    pr.session = {"user": "admin", "location_code": 7}
    loc = 7
    hdr = pr._detect_table(["LPOHDR", "lpohdr"])
    no_col = pr._detect_column(hdr, ["LPONO", "LPO_NO", "lpono"])
    loc_col = pr._detect_column(hdr, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"])
    del_col = pr._detect_column(hdr, ["DELFLAG", "DEL_FLAG", "delflag"])
    date_col = pr._detect_column(hdr, ["LPODATE", "LPO_DATE", "lpodate"])
    amt_col = pr._detect_column(hdr, ["LPOAMOUNT", "LPO_AMOUNT", "lpoamount"])
    sup_col = pr._detect_column(hdr, ["SUPPLIERCODE", "SUPPLIER_CODE", "suppliercode"])
    created = pr._detect_column(hdr, ["CREATEDDATE", "CREATED_DATE", "createddate"])
    h = hdr
    approval_join, pa_status, _ = pr._lpo_list_approval_join(h, no_col, loc, "draft")
    tab_where = pr._lpo_list_tab_where(pa_status, "draft", bool(approval_join), False)
    where_parts = [f"{h}.{loc_col} = :loc", f"NVL({h}.{del_col}, 'N') = 'N'", tab_where]
    where_sql = " AND ".join(where_parts)
    params = {"loc": loc}

    def timed(label, fn):
        t0 = time.perf_counter()
        fn()
        print(f"{label}: {time.perf_counter() - t0:.3f}s")

    # COUNT without supplier join
    cq_nosupp = f"SELECT COUNT(*) AS cnt FROM {h} {approval_join} WHERE {where_sql}"
    timed("COUNT (no supplier join)", lambda: pr._fetch_rows(cq_nosupp, dict(params)))

    # COUNT with supplier join (current)
    supp_tbl = pr._detect_table(["SUPPLIER", "supplier", "SUPPLIERS"])
    sup_code = pr._detect_column(supp_tbl, ["SUPPLIERCODE", "SUPPLIER_CODE", "suppliercode"])
    sup_name = pr._detect_column(supp_tbl, ["SUPPLIERNAME", "SUPPLIER_NAME", "suppliername"])
    s_loc = pr._detect_column(supp_tbl, ["LOCATIONCODE", "LOCATION_CODE", "locationcode"])
    sup_join = f" LEFT JOIN {supp_tbl} s ON {h}.{sup_col} = s.{sup_code} AND {h}.{loc_col} = s.{s_loc} "
    cq_supp = f"SELECT COUNT(*) AS cnt FROM {h} {approval_join} {sup_join} WHERE {where_sql}"
    timed("COUNT (with supplier join)", lambda: pr._fetch_rows(cq_supp, dict(params)))

    # PAGE 50 without supplier
    cols = f"{h}.{no_col} lpono, {h}.{date_col} lpodate"
    base = f"SELECT {cols} FROM {h} {approval_join} WHERE {where_sql} ORDER BY {h}.{no_col} DESC"
    pq = (
        f"SELECT lpono, lpodate FROM (SELECT inner_q.*, ROWNUM rnum FROM ({base}) inner_q "
        f"WHERE ROWNUM <= 50) WHERE rnum > 0"
    )
    timed("PAGE 50 (no supplier)", lambda: pr._fetch_rows(pq, dict(params)))

    # PAGE 50 with supplier
    cols2 = (
        f"{h}.{no_col} lpono, {h}.{date_col} lpodate, s.{sup_name} suppliername, "
        f"NVL({h}.{amt_col},0) amount"
    )
    base2 = f"SELECT {cols2} FROM {h} {approval_join} {sup_join} WHERE {where_sql} ORDER BY {h}.{no_col} DESC"
    pq2 = (
        f"SELECT lpono FROM (SELECT inner_q.*, ROWNUM rnum FROM ({base2}) inner_q "
        f"WHERE ROWNUM <= 50) WHERE rnum > 0"
    )
    timed("PAGE 50 (with supplier)", lambda: pr._fetch_rows(pq2, dict(params)))

    print("--- full function (3 runs) ---")
    for i in range(3):
        t0 = time.perf_counter()
        rows, total = pr._get_lpo_list_page(1, 50, "draft")
        print(f"full #{i+1}: {time.perf_counter() - t0:.3f}s rows={len(rows)} total={total}")

    print("--- approved tab ---")
    t0 = time.perf_counter()
    rows, total = pr._get_lpo_list_page(1, 50, "approved")
    print(f"approved: {time.perf_counter() - t0:.3f}s rows={len(rows)} total={total}")

    print("--- overhead probes ---")
    t0 = time.perf_counter()
    for _ in range(20):
        pr._detect_table(["LPOHDR", "lpohdr"])
        pr._detect_table(["SUPPLIER", "supplier", "SUPPLIERS"])
        pr._detect_table(["RECEIPTHDR", "receipthdr"])
    print(f"_detect_table x20*3: {time.perf_counter() - t0:.3f}s")

    t0 = time.perf_counter()
    for _ in range(20):
        pr._table_exists("PURCHASE_APPROVAL_TXN")
    print(f"_table_exists x20: {time.perf_counter() - t0:.3f}s")

    lpo_nos = [r["lpono"] for r in (rows or [])[:50]]
    t0 = time.perf_counter()
    pr._lpo_list_receipt_lpo_set(lpo_nos, loc)
    print(f"receipt batch 50: {time.perf_counter() - t0:.3f}s")

    # simulate page route (SSR + no API)
    t0 = time.perf_counter()
    pr._get_lpo_list_page(1, 50, "draft")
    print(f"SSR simulate: {time.perf_counter() - t0:.3f}s")
