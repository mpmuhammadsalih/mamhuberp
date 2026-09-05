# Storefront API (MamaHub → Nova)

Customer-facing REST API mounted at **`/api/v1/*`**, compatible with the MamaHub React storefront.

Registered via addon `addons/storefront_api` → `storefront_backend:bp`.

## Implemented endpoints

- `GET /api/v1/health`, `/health/live`, `/health/ready`
- `GET /api/v1/storefront/home`, `/media`, `/media/files/{filename}`
- `GET /api/v1/products`, `/products/{code}`, `/categories/tree`, `/brands`, `/age-groups`, `/interests`
- `POST /api/v1/customer/auth/register`, `/customer/auth/login`, `GET /customer/auth/me`
- `GET|POST|PATCH|DELETE /api/v1/cart/...`, `POST /cart/coupon`
- `POST /api/v1/checkout/start`, `/delivery`, `/pickup`, `/coupon`, `/confirm`, `GET /checkout/review`, `/payment-methods`
- `GET /api/v1/orders`, `/orders/{id}`, `/orders/track/{number}`, `POST /orders/{id}/cancel`
- `GET|POST|PATCH|DELETE /api/v1/addresses/...`
- `GET /api/v1/delivery/zones`, `/delivery/slots`, `/pickup/stores`, geocode + estimate
- `GET /api/v1/wishlist`, wishlist item CRUD, move-to-cart
- `GET /api/v1/loyalty/dashboard`, `/loyalty/rules`
- `GET /api/v1/notifications`, unread count, mark read
- `GET /api/v1/reviews/products/{code}`, `POST /reviews`
- `GET /api/v1/cms/pages`, `/cms/pages/{slug}`
- `GET /api/v1/search/products`, `/search/suggest`
- `GET /api/v1/gift-finder`
- `GET /api/v1/promotions/coupons`

## Admin API (React `/admin/*` SPA)

- `POST /api/v1/admin/auth/login`, `GET /admin/auth/me` — staff login (APP_USER + ADMIN/SUPER_ADMIN role)
- `GET /api/v1/admin/dashboard`, `/admin/orders`, `/admin/products`, `/admin/promotions`, etc.
- `GET /api/v1/reviews/admin/pending`, `PATCH /reviews/admin/{id}/status`

Legacy catch-all `/admin/*` and `/reviews/admin/*` 501 handlers are removed once specific routes are registered first.

## Pending (501)

None — use Nova ERP Ecommerce menu (`/ecommerce/*`) as an alternative admin UI.

## Config

Uses Nova `.env`:

- `JWT_SECRET_KEY` — customer JWT signing (same as mobile API)
- `DEFAULT_LOCATION_CODE` — catalog branch scope (default `1`)
- `TAX_RATE` — checkout tax rate (default `0`)
- `CHECKOUT_SESSION_TTL_SECONDS` — in-memory checkout session TTL (default `1800`)

Install dependency: `pip install bcrypt` (listed in Nova `requirements.txt`).
