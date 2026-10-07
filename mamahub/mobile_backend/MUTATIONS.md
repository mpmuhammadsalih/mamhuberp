# Mobile API — mutations, transactions, session lock, save-once

Standard pattern for all **write** endpoints and services in `mobile_backend/`.

## 1. Oracle transactions

All insert / update / delete work must commit or rollback as one unit.

```python
from mobile_backend.database.oracle_pool import get_connection
from mobile_backend.database.transaction import oracle_transaction

conn = get_connection(tenant_id=tenant_id)
with oracle_transaction(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ...")
        cur.execute("UPDATE ...")
# commit on success, rollback on any exception
```

**Do not** scatter `conn.commit()` / manual try/rollback in services. Use `oracle_transaction`.

Read-only endpoints: plain `with conn.cursor()` is enough.

ERP-wrapper services (PO/GRN/sales that call desktop helpers) often commit inside ERP code. Still wrap mobile-owned SQL in `oracle_transaction`, and always use the session lock + save-nonce below.

## 2. Session / operation lock

Serialize concurrent saves for the same user + document (complements save-nonce).

| Component | File |
|-----------|------|
| Per-user/doc TTL lock | `operation_lock.py` (`mobile_operation_lock`) |
| Busy → HTTP 423 | `mutation_errors.py` (`failure_from_mutation_exc`) |

```python
from mobile_backend.operation_lock import mobile_operation_lock

with mobile_operation_lock(
    "purchase_order",
    doc_id,
    busy_message="Purchase order is already being saved. Please wait.",
):
    # save / post work
```

Route handlers should catch exceptions with `failure_from_mutation_exc` so `OperationBusyError` returns **423**.

## 3. Save-once (replay protection)

Prevents duplicate saves from double-tap, retries, or stale tokens (same idea as ERP `save_nonce.py`).

| Component | File |
|-----------|------|
| Per-user one-time token | `save_guard.py` |
| FastAPI dependency | `deps_save.py` |
| 409 replay response | `bootstrap.py` (`SaveNonceReplayError`) |
| Token on login | `routes/auth_routes.py` |
| Refresh token | `GET /api/v1/auth/save-nonce` |

### Adding a new mutation route

```python
from fastapi import APIRouter, Depends, Request
from mobile_backend.deps_save import require_save_nonce, success_after_mutation
from mobile_backend.mutation_errors import failure_from_mutation_exc

@router.post("/widgets", dependencies=[Depends(require_access_claims), require_save_nonce])
def create_widget(request: Request, body: WidgetBody):
    try:
        data = widget_service.create(body.model_dump())
    except Exception as exc:
        return failure_from_mutation_exc(exc, fallback="Failed to save widget.")
    return success_after_mutation(request, data, message="Saved", status_code=201)
```

### Exempt paths (no save-nonce)

- All **GET**
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

### Response shape after success

```json
{
  "success": true,
  "message": "Saved",
  "data": { ... },
  "save_nonce": "<new-one-time-token>"
}
```

### Duplicate save (409)

```json
{
  "success": false,
  "message": "Duplicate or invalid save request...",
  "replay_blocked": true,
  "save_nonce": "<fresh-token>"
}
```

### Concurrent save (423)

```json
{
  "success": false,
  "message": "A save is already in progress for this document. Please wait until it completes."
}
```

## 4. Flutter client (automatic)

The Flutter app (`Nova_Mobile/flutter_app`) handles:

- `X-Save-Nonce` header on POST/PUT/PATCH/DELETE via `ApiClient`
- Token rotation from `save_nonce` in responses
- Global **Saving…** overlay via `TransactionOverlayController`

New mobile features only need to call existing services through `ApiClient` — no extra client wiring.

## Checklist for new features

- [ ] Service: mobile-owned writes inside `oracle_transaction`
- [ ] Service: `mobile_operation_lock` around save/post/cancel
- [ ] Route: `require_save_nonce` on dependencies
- [ ] Route: `success_after_mutation(request, ...)` on success (not plain `success()`)
- [ ] Route: `failure_from_mutation_exc` for busy (423) / validation (400)
- [ ] Flutter: use `ApiClient` / existing `*Service` classes
- [ ] Test: double submit → one success, one 409; concurrent → 423; overlay blocks UI during save

## Reference implementations

| Area | Routes | Services |
|------|--------|----------|
| GRN / PO / Return | `routes/purchase_routes.py` | `grn_service.py`, `purchase_order_service.py`, `purchase_return_service.py` |
| Stock adjustment | `routes/stock_adjustment_routes.py` | `stock_adjustment_service.py` |
| Cash payment voucher | `routes/accounts_routes.py` | `cash_payment_voucher_service.py` |
| Stock count | `routes/stock_count_routes.py` | `stock_count_service.py` |
| Stock transfer | `routes/stock_transfer_routes.py` | `stock_transfer_service.py` |
| Sales | `routes/sales_routes.py` | `sales_invoice_service.py`, `sales_order_service.py` |
