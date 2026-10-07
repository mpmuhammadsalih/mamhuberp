"""
Ensure inventory-related chart of accounts exist (1300, 5199, COGS, etc.).
Run from project root: python -m scripts.seed_inventory_chart_of_accounts
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import INVENTORY_COA_ACCOUNTS, ensure_inventory_chart_of_accounts, get_all_chart_of_accounts


def main() -> None:
    stats = ensure_inventory_chart_of_accounts()
    print('Inventory COA ensure:', stats)
    codes = {str(r.get('code') or r.get('account_code') or '').strip() for r in (get_all_chart_of_accounts() or [])}
    print('\nInventory accounts:')
    for spec in INVENTORY_COA_ACCOUNTS:
        code = spec['code']
        mark = 'OK' if code in codes else 'MISSING'
        print(f"  [{mark}] {code} — {spec['name']} ({spec['account_type']})")
    if stats.get('errors'):
        sys.exit(1)


if __name__ == '__main__':
    main()
