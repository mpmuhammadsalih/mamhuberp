"""Nexa Mobile JWT API — `/api/v1/*` for Flutter app."""
from fastapi import Depends
from nexa_http import Blueprint

from mobile_backend.deps_oracle import mobile_oracle_scope_dep

bp = Blueprint("mobile_api", __name__, dependencies=[Depends(mobile_oracle_scope_dep)])

from mobile_backend.routes import (  # noqa: E402
    accounts_routes,
    auth_routes,
    config_routes,
    customer_routes,
    dashboard_routes,
    inventory_routes,
    item_routes,
    purchase_routes,
    reports_routes,
    sales_routes,
    stock_adjustment_routes,
    stock_count_routes,
    stock_transfer_routes,
    supplier_routes,
    tenant_routes,
)

for _router in (
    config_routes.router,
    auth_routes.router,
    dashboard_routes.router,
    inventory_routes.router,
    stock_count_routes.router,
    stock_transfer_routes.router,
    stock_adjustment_routes.router,
    accounts_routes.router,
    sales_routes.router,
    purchase_routes.router,
    reports_routes.router,
    customer_routes.router,
    supplier_routes.router,
    item_routes.router,
    tenant_routes.router,
):
    bp.include_router(_router)
