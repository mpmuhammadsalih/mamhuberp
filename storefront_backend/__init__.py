"""MamaHub storefront REST API mounted at /api/v1 (customer-facing)."""
from __future__ import annotations

from fastapi import Depends
from nexa_http import Blueprint

from mobile_backend.deps_oracle import mobile_oracle_scope_dep

bp = Blueprint('storefront_api', __name__, dependencies=[Depends(mobile_oracle_scope_dep)])

from storefront_backend.routes import (  # noqa: E402
    addresses_routes,
    admin_auth_routes,
    admin_routes,
    auth_routes,
    cart_routes,
    catalog_routes,
    checkout_routes,
    cms_routes,
    delivery_routes,
    gift_finder_routes,
    health_routes,
    inbox_routes,
    loyalty_routes,
    notifications_routes,
    orders_routes,
    pending_routes,
    reviews_admin_routes,
    reviews_routes,
    search_routes,
    seo_routes,
    storefront_routes,
    wishlist_routes,
)

for _router in (
    health_routes.router,
    storefront_routes.router,
    catalog_routes.router,
    auth_routes.router,
    cart_routes.router,
    checkout_routes.router,
    orders_routes.router,
    addresses_routes.router,
    delivery_routes.router,
    wishlist_routes.router,
    loyalty_routes.router,
    notifications_routes.router,
    inbox_routes.router,
    reviews_routes.router,
    cms_routes.router,
    search_routes.router,
    seo_routes.router,
    gift_finder_routes.router,
    admin_auth_routes.router,
    admin_routes.router,
    reviews_admin_routes.router,
    pending_routes.router,
):
    bp.include_router(_router, prefix='/api/v1')
