"""
Backfill ITEMJOURNEL (preferred) or ITEMJOURNAL from posted GRNs, BILL sales lines,
and posted purchase returns.

Usage (single-DB / default tenant connection from .env):
  python scripts/backfill_itemjournal.py
  python scripts/backfill_itemjournal.py --dry-run
  python scripts/backfill_itemjournal.py --location 1
  python scripts/backfill_itemjournal.py --prefer-journal

Multi-DB: set tenant in session or use app_context / db helpers, e.g.:
  python -c "from nexa_http.context import app_context; ..."
  >>> from db import backfill_itemjournal_from_documents, _get_connection
  >>> with _get_connection() as c:
  ...     ok, msg, s = backfill_itemjournal_from_documents(c, location_code=1)
  ...     c.commit()
  >>> print(ok, msg, s)
"""
from __future__ import annotations
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

def main() -> int:
    parser = argparse.ArgumentParser(description='Backfill ITEMJOURNEL / ITEMJOURNAL from ERP documents.')
    parser.add_argument('--dry-run', action='store_true', help='Count only; no INSERT/commit.')
    parser.add_argument('--location', type=int, default=None, help='Limit to this LOCATIONCODE.')
    parser.add_argument('--prefer-journal', action='store_true', help='Use ITEMJOURNAL if present instead of preferring ITEMJOURNEL.')
    parser.add_argument('--no-grn', action='store_true')
    parser.add_argument('--no-sales', action='store_true')
    parser.add_argument('--no-pr', action='store_true')
    args = parser.parse_args()
    try:
        from nexa_http.context import app_context
    except Exception as e:
        print('Could not import app_context:', e, file=sys.stderr)
        return 1
    with app_context():
        from db import backfill_itemjournal_from_documents
        ok, msg, stats = backfill_itemjournal_from_documents(None, location_code=args.location, prefer_itemjournel=not args.prefer_journal, include_grn=not args.no_grn, include_sales=not args.no_sales, include_purchase_return=not args.no_pr, dry_run=args.dry_run)
        print(msg, flush=True)
        print(stats, flush=True)
        return 0 if ok else 1
if __name__ == '__main__':
    raise SystemExit(main())
