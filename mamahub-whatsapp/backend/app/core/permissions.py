"""Role-based access control."""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Set


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    SALES = "SALES"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"


class Permission(str, Enum):
    CHATS_MANAGE = "chats.manage"
    PRODUCTS_SEARCH = "products.search"
    ORDERS_CREATE = "orders.create"
    ORDERS_VIEW = "orders.view"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_EDIT = "customers.edit"
    USERS_MANAGE = "users.manage"
    SETTINGS_MANAGE = "settings.manage"
    TEMPLATES_MANAGE = "templates.manage"
    REPORTS_VIEW = "reports.view"
    AI_USE = "ai.use"


ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),
    Role.ADMIN: {
        Permission.CHATS_MANAGE,
        Permission.PRODUCTS_SEARCH,
        Permission.ORDERS_CREATE,
        Permission.ORDERS_VIEW,
        Permission.CUSTOMERS_VIEW,
        Permission.CUSTOMERS_EDIT,
        Permission.USERS_MANAGE,
        Permission.SETTINGS_MANAGE,
        Permission.TEMPLATES_MANAGE,
        Permission.REPORTS_VIEW,
        Permission.AI_USE,
    },
    Role.SALES: {
        Permission.CHATS_MANAGE,
        Permission.PRODUCTS_SEARCH,
        Permission.ORDERS_CREATE,
        Permission.ORDERS_VIEW,
        Permission.CUSTOMERS_VIEW,
        Permission.CUSTOMERS_EDIT,
        Permission.AI_USE,
    },
    Role.CUSTOMER_SERVICE: {
        Permission.CHATS_MANAGE,
        Permission.PRODUCTS_SEARCH,
        Permission.CUSTOMERS_VIEW,
        Permission.CUSTOMERS_EDIT,
        Permission.ORDERS_VIEW,
        Permission.AI_USE,
    },
}


def permissions_for(role: str) -> Set[str]:
    try:
        resolved = Role(role)
    except ValueError:
        return set()
    return {item.value for item in ROLE_PERMISSIONS.get(resolved, set())}


def has_permission(role: str, required: Permission | Iterable[Permission]) -> bool:
    granted = permissions_for(role)
    if isinstance(required, Permission):
        return required.value in granted
    return all(item.value in granted for item in required)
