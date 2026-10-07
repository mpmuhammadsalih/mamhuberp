"""Create STOCK_COUNT_HDR / STOCK_COUNT_DTL for mobile + ERP stock counting.

Idempotent — safe to re-run. Uses the same DDL as addons.warehouse.stock_count_db.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from addons.warehouse.stock_count_db import ensure_stock_count_tables
from config.settings import is_multi_db_mode
from db import get_tenant_config, get_tenant_list, set_active_db_key


def main() -> None:
    if is_multi_db_mode():
        tenants = get_tenant_list() or []
        if not tenants:
            print("No active tenants found.")
            return
        for t in tenants:
            tid = (t.get("tenant_id") or "").strip()
            if not tid:
                continue
            get_tenant_config(tid)
            set_active_db_key(tid)
            ok = ensure_stock_count_tables()
            print(f"[TENANT:{tid}] ensure_stock_count_tables -> {ok}")
    else:
        ok = ensure_stock_count_tables()
        print(f"[DEFAULT_DB] ensure_stock_count_tables -> {ok}")


if __name__ == "__main__":
    main()
