"""Chart of Accounts model (mirrors D:\\Webapplication\\Accountsmanagement\\app\\models\\chart_of_accounts.py)."""
from typing import Any, Dict, List, Optional
from db import ACCOUNT_TYPES, ACCOUNT_STATUSES, COA_DEFAULT_CURRENCY, ensure_chart_of_accounts_table, get_all_chart_of_accounts, get_chart_of_account_by_id, get_chart_of_account_by_code, create_chart_of_account as db_create, update_chart_of_account as db_update, delete_chart_of_account as db_delete, get_chart_of_accounts_tree as db_get_tree, chart_of_account_has_children as db_has_children

class ChartOfAccounts:
    """Chart of Accounts model (reference: Accountsmanagement)."""
    TYPE_ASSET = 'ASSET'
    TYPE_LIABILITY = 'LIABILITY'
    TYPE_EQUITY = 'EQUITY'
    TYPE_REVENUE = 'REVENUE'
    TYPE_EXPENSE = 'EXPENSE'
    ACCOUNT_TYPES = list(ACCOUNT_TYPES)
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'
    STATUS_SUSPENDED = 'SUSPENDED'

    @staticmethod
    def create(account_data: Dict[str, Any], db_key: Optional[str]=None) -> int:
        """Create a new chart of accounts entry. Returns account_id."""
        ensure_chart_of_accounts_table(db_key=db_key)
        return db_create(code=account_data['code'], name=account_data['name'], account_type=account_data['type'], parent_id=account_data.get('parent_id'), is_postable=account_data.get('is_postable', True), currency=account_data.get('currency') or COA_DEFAULT_CURRENCY, status=account_data.get('status', ChartOfAccounts.STATUS_ACTIVE), company_id=account_data.get('company_id'), branch_id=account_data.get('branch_id'), locationcode=account_data.get('locationcode'), db_key=db_key)

    @staticmethod
    def get_by_id(account_id: int, db_key: Optional[str]=None) -> Optional[Dict[str, Any]]:
        """Get account by ID."""
        return get_chart_of_account_by_id(account_id, db_key=db_key)

    @staticmethod
    def get_by_code(code: str, db_key: Optional[str]=None) -> Optional[Dict[str, Any]]:
        """Get account by code."""
        return get_chart_of_account_by_code(code, db_key=db_key)

    @staticmethod
    def get_all(filters: Optional[Dict[str, Any]]=None, limit: int=100, offset: int=0, db_key: Optional[str]=None, raise_on_error: bool=False) -> List[Dict[str, Any]]:
        """Get all accounts with optional filters. limit/offset applied in memory for compatibility."""
        ensure_chart_of_accounts_table(db_key=db_key)
        rows = get_all_chart_of_accounts(db_key=db_key, raise_on_error=raise_on_error)
        if filters:
            if 'type' in filters:
                rows = [r for r in rows if (r.get('type') or '').upper() == (filters['type'] or '').upper()]
            if 'status' in filters:
                rows = [r for r in rows if (r.get('status') or '').upper() == (filters['status'] or '').upper()]
            if 'is_postable' in filters:
                rows = [r for r in rows if r.get('is_postable') == filters['is_postable']]
            if 'parent_id' in filters:
                rows = [r for r in rows if r.get('parent_id') == filters['parent_id']]
        return rows[offset:offset + limit] if limit or offset else rows

    @staticmethod
    def get_tree(db_key: Optional[str]=None) -> List[Dict[str, Any]]:
        """Get hierarchical tree structure of accounts (ACTIVE only)."""
        return db_get_tree(db_key=db_key)

    @staticmethod
    def update(account_id: int, account_data: Dict[str, Any], db_key: Optional[str]=None) -> bool:
        """Update an account."""
        return db_update(account_id=account_id, name=account_data.get('name'), account_type=account_data.get('type'), parent_id=account_data.get('parent_id'), is_postable=account_data.get('is_postable'), currency=account_data.get('currency'), status=account_data.get('status'), company_id=account_data.get('company_id'), branch_id=account_data.get('branch_id'), locationcode=account_data.get('locationcode'), db_key=db_key)

    @staticmethod
    def has_children(account_id: int, db_key: Optional[str]=None) -> bool:
        """Check if account has children."""
        return db_has_children(account_id, db_key=db_key)

    @staticmethod
    def delete(account_id: int, db_key: Optional[str]=None) -> None:
        """Delete an account. Raises ValueError if it has children."""
        db_delete(account_id, db_key=db_key)
