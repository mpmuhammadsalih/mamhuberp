"""Add LPOHDR.NEXA_GRN_STATUS for mobile goods-receiving finalize.

Default Pending; mobile finalize-receiving sets Completed.
Idempotent — safe to re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config.settings import is_multi_db_mode
from db import _get_connection, get_tenant_config, get_tenant_list
from db.oracle_driver import oracle_connect

COL = "NEXA_GRN_STATUS"
DDL = (
    f"ALTER TABLE LPOHDR ADD ({COL} VARCHAR2(40) DEFAULT 'Pending' NOT NULL)"
)


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
        {"t": table_name.upper()},
    )
    return int(cur.fetchone()[0] or 0) > 0


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) FROM user_tab_columns
         WHERE table_name = :t AND column_name = :c
        """,
        {"t": table_name.upper(), "c": column_name.upper()},
    )
    return int(cur.fetchone()[0] or 0) > 0


def _install(conn, label: str) -> None:
    with conn.cursor() as cur:
        if not _table_exists(cur, "LPOHDR"):
            print(f"[{label}] LPOHDR not found — skip")
            return
        if _column_exists(cur, "LPOHDR", COL):
            print(f"[{label}] LPOHDR.{COL} already exists — skip")
            return
        cur.execute(DDL)
        conn.commit()
    print(f"[{label}] Added LPOHDR.{COL}")


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
            cfg = get_tenant_config(tid)
            with oracle_connect(
                user=cfg["user"],
                password=cfg["password"],
                dsn=cfg["dsn"],
            ) as conn:
                _install(conn, f"TENANT:{tid}")
    else:
        with _get_connection() as conn:
            _install(conn, "DEFAULT_DB")


if __name__ == "__main__":
    main()
