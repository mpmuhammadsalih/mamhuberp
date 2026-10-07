"""Shopping cart via MH_CART tables."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.deps import resolve_location_code
from storefront_backend.services.catalog import effective_unit_price, _float_price
from addons.ecommerce.services import product_web_meta as web_meta_svc
from storefront_backend.services.item_images import public_item_image_url
from storefront_backend.services import promotions as promo_svc
from storefront_backend.services.schema_bootstrap import (
    ensure_cart_item_parent_column,
    ensure_cart_schema,
    _invalidate_cart_table_cache,
)

try:
    from addons.ecommerce import settings_store as ecommerce_settings
except ImportError:  # pragma: no cover
    ecommerce_settings = None


def _coupons_enabled() -> bool:
    if ecommerce_settings is None:
        return False
    return ecommerce_settings.coupons_enabled()

_CART_SCHEMA_OK: bool | None = None
_PARENT_COL_OK: bool | None = None


def _has_parent_column() -> bool:
    global _PARENT_COL_OK
    if _PARENT_COL_OK is True:
        return True
    try:
        ensure_cart_item_parent_column()
        _PARENT_COL_OK = True
        return True
    except Exception:
        _PARENT_COL_OK = False
        return False


def _parent_int(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _cart_item_select_sql() -> str:
    parent_sql = (
        'PARENT_ITEM_CODE AS parent_item_code'
        if _has_parent_column()
        else 'NULL AS parent_item_code'
    )
    return f"""
        SELECT
            CART_ITEM_ID AS cart_item_id,
            ITEM_CODE AS item_code,
            LOCATION_CODE AS location_code,
            QUANTITY AS quantity,
            UNIT_PRICE AS unit_price,
            LINE_STATUS AS line_status,
            {parent_sql}
        FROM MH_CART_ITEM
        WHERE CART_ID = :cart_id AND LINE_STATUS = 'ACTIVE'
        ORDER BY CART_ITEM_ID
    """


def _lookup_item_price(item_code: int, location_code: int) -> Optional[float]:
    """Lightweight price lookup for cart — uses offer price when below retail."""
    rows = _safe_rows(
        """
        SELECT
            NVL(RETAILPRICE, 0) AS retailprice,
            NVL(WHOLESALEPRICE, 0) AS wholesaleprice
        FROM ITEMMASTER
        WHERE ITEMCODE = :item_code
          AND LOCATIONCODE = :location_code
          AND ROWNUM = 1
        """,
        {'item_code': int(item_code), 'location_code': int(location_code)},
    )
    if not rows:
        return None
    row = rows[0]
    retail = _float_price(row.get('retailprice') or row.get('RETAILPRICE'))
    wholesale = _float_price(row.get('wholesaleprice') or row.get('WHOLESALEPRICE'))
    resolved_offer = web_meta_svc.resolve_offer_price(
        item_code,
        wholesale_price=wholesale,
    )
    if resolved_offer is not None:
        wholesale = resolved_offer
    return effective_unit_price(retail, wholesale)


def _cart_ready() -> bool:
    global _CART_SCHEMA_OK
    if _CART_SCHEMA_OK is True:
        return True
    if _table_exists('MH_CART') and _table_exists('MH_CART_ITEM'):
        try:
            ensure_cart_item_parent_column()
        except Exception:
            pass
        _CART_SCHEMA_OK = True
        return True
    try:
        ensure_cart_schema()
        ensure_cart_item_parent_column()
    except Exception:
        _invalidate_cart_table_cache()
        _CART_SCHEMA_OK = False
        return False
    ready = _table_exists('MH_CART') and _table_exists('MH_CART_ITEM')
    _CART_SCHEMA_OK = ready
    return ready


def _next_id(sequence: str) -> int:
    rows = _safe_rows(f'SELECT {sequence}.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _fetch_cart(cart_id: int) -> Optional[Dict[str, Any]]:
    headers = _safe_rows(
        """
        SELECT
            CART_ID AS cart_id,
            USER_ID AS user_id,
            GUEST_TOKEN AS guest_token,
            LOCATION_CODE AS location_code,
            CART_STATUS AS cart_status,
            CURRENCY_CODE AS currency_code
        FROM MH_CART
        WHERE CART_ID = :cart_id
        """,
        {'cart_id': int(cart_id)},
    )
    if not headers:
        return None
    cart = dict(headers[0])
    items = _safe_rows(
        _cart_item_select_sql(),
        {'cart_id': int(cart_id)},
    )
    cart['items'] = items
    return cart


def _cart_coupon_discount(cart_id: int) -> float:
    if not _table_exists('MH_CART_COUPON'):
        return 0.0
    rows = _safe_rows(
        """
        SELECT NVL(SUM(DISCOUNT_AMOUNT), 0) AS discount_total
        FROM MH_CART_COUPON
        WHERE CART_ID = :cart_id
        """,
        {'cart_id': int(cart_id)},
    )
    return float(rows[0]['discount_total']) if rows else 0.0


def _lookup_cart_product_meta(
    items: List[Dict[str, Any]],
    *,
    default_location_code: int,
) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """Bulk-fetch item names/images for cart lines (one query per location)."""
    if not items:
        return {}

    grouped: Dict[int, List[int]] = {}
    for row in items:
        loc = int(row.get('location_code') or default_location_code)
        code = int(row.get('item_code') or row.get('ITEM_CODE') or 0)
        if code <= 0:
            continue
        bucket = grouped.setdefault(loc, [])
        if code not in bucket:
            bucket.append(code)

    meta: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for loc, codes in grouped.items():
        if not codes:
            continue
        placeholders = ', '.join(f':ic{i}' for i in range(len(codes)))
        params: Dict[str, Any] = {'loc': loc}
        for i, code in enumerate(codes):
            params[f'ic{i}'] = code
        rows = _safe_rows(
            f"""
            SELECT
                ITEMCODE AS item_code,
                ITEMNAME AS itemname,
                IMAGE_PATH AS image_path
            FROM ITEMMASTER
            WHERE LOCATIONCODE = :loc
              AND ITEMCODE IN ({placeholders})
            """,
            params,
        )
        if not rows:
            rows = _safe_rows(
                f"""
                SELECT ITEMCODE AS item_code, ITEMNAME AS itemname
                FROM ITEMMASTER
                WHERE LOCATIONCODE = :loc
                  AND ITEMCODE IN ({placeholders})
                """,
                params,
            )
        for row in rows:
            item_code = int(row.get('item_code') or row.get('ITEMCODE') or 0)
            if item_code <= 0:
                continue
            name = row.get('itemname') or row.get('ITEMNAME') or ''
            image = row.get('image_path') or row.get('IMAGE_PATH')
            meta[(loc, item_code)] = {
                'item_name': str(name).strip() if name is not None else '',
                'primary_image_url': public_item_image_url(str(image).strip() if image else None),
            }

        missing_codes = [code for code in codes if (loc, code) not in meta]
        if missing_codes:
            placeholders2 = ', '.join(f':mic{i}' for i in range(len(missing_codes)))
            params2: Dict[str, Any] = {}
            for i, code in enumerate(missing_codes):
                params2[f'mic{i}'] = code
            fallback_rows = _safe_rows(
                f"""
                SELECT item_code, itemname, image_path FROM (
                    SELECT im.ITEMCODE AS item_code,
                           im.ITEMNAME AS itemname,
                           im.IMAGE_PATH AS image_path,
                           ROW_NUMBER() OVER (PARTITION BY im.ITEMCODE ORDER BY im.LOCATIONCODE) AS rn
                    FROM ITEMMASTER im
                    WHERE im.ITEMCODE IN ({placeholders2})
                )
                WHERE rn = 1
                """,
                params2,
            )
            if not fallback_rows:
                fallback_rows = _safe_rows(
                    f"""
                    SELECT item_code, itemname FROM (
                        SELECT im.ITEMCODE AS item_code,
                               im.ITEMNAME AS itemname,
                               ROW_NUMBER() OVER (PARTITION BY im.ITEMCODE ORDER BY im.LOCATIONCODE) AS rn
                        FROM ITEMMASTER im
                        WHERE im.ITEMCODE IN ({placeholders2})
                    )
                    WHERE rn = 1
                    """,
                    params2,
                )
            for row in fallback_rows:
                item_code = int(row.get('item_code') or row.get('ITEMCODE') or 0)
                if item_code <= 0 or (loc, item_code) in meta:
                    continue
                name = row.get('itemname') or row.get('ITEMNAME') or ''
                image = row.get('image_path') or row.get('IMAGE_PATH')
                meta[(loc, item_code)] = {
                    'item_name': str(name).strip() if name is not None else '',
                    'primary_image_url': public_item_image_url(str(image).strip() if image else None),
                }
    return meta


def _build_response(
    cart: Dict[str, Any],
    *,
    discount_total: Optional[float] = None,
    include_product_meta: bool = True,
) -> Dict[str, Any]:
    lines: List[Dict[str, Any]] = []
    subtotal = 0.0
    cart_loc = int(cart.get('location_code') or 1)
    product_meta = (
        _lookup_cart_product_meta(cart.get('items') or [], default_location_code=cart_loc)
        if include_product_meta
        else {}
    )
    for item in cart.get('items') or []:
        qty = float(item.get('quantity') or 0)
        unit = float(item.get('unit_price') or 0)
        line_total = round(qty * unit, 2)
        subtotal += line_total
        item_code = int(item['item_code'])
        line_loc = int(item.get('location_code') or cart_loc)
        details = product_meta.get((line_loc, item_code), {})
        parent_item_code = _parent_int(
            item.get('parent_item_code') or item.get('PARENT_ITEM_CODE')
        )
        lines.append({
            'cart_item_id': int(item['cart_item_id']),
            'item_code': item_code,
            'location_code': line_loc,
            'quantity': qty,
            'unit_price': unit,
            'line_total': line_total,
            'line_status': item.get('line_status') or 'ACTIVE',
            'parent_item_code': parent_item_code,
            'is_addon': bool(parent_item_code) or web_meta_svc.is_addon_item(item_code),
            'product': {
                'item_code': item_code,
                'item_name': details.get('item_name') or '',
                'primary_image_url': details.get('primary_image_url'),
            },
        })
    children_by_parent: Dict[int, List[Dict[str, Any]]] = {}
    mains: List[Dict[str, Any]] = []
    for line in lines:
        parent = _parent_int(line.get('parent_item_code'))
        if parent:
            children_by_parent.setdefault(parent, []).append(line)
        else:
            mains.append(line)
    ordered: List[Dict[str, Any]] = []
    for main in mains:
        ordered.append(main)
        ordered.extend(children_by_parent.pop(int(main['item_code']), []))
    for leftover in children_by_parent.values():
        ordered.extend(leftover)
    lines = ordered
    if discount_total is None:
        discount_total = _cart_coupon_discount(int(cart['cart_id']))
    taxable = max(subtotal - discount_total, 0)
    return {
        'cart_id': int(cart['cart_id']),
        'guest_token': cart.get('guest_token'),
        'location_code': int(cart.get('location_code') or 1),
        'cart_status': cart.get('cart_status') or 'ACTIVE',
        'items': lines,
        'summary': {
            'subtotal': round(subtotal, 2),
            'discount_total': round(discount_total, 2),
            'tax_total': 0.0,
            'grand_total': round(taxable, 2),
            'currency_code': cart.get('currency_code') or 'QAR',
            'item_count': len(lines),
        },
    }


def _find_active_cart(*, user_id: Optional[int], guest_token: Optional[str]) -> Optional[Dict[str, Any]]:
    if user_id is not None:
        rows = _safe_rows(
            """
            SELECT CART_ID AS cart_id FROM MH_CART
            WHERE USER_ID = :user_id AND CART_STATUS IN ('ACTIVE', 'CHECKOUT')
            ORDER BY CART_ID DESC
            """,
            {'user_id': int(user_id)},
        )
    elif guest_token:
        rows = _safe_rows(
            """
            SELECT CART_ID AS cart_id FROM MH_CART
            WHERE GUEST_TOKEN = :guest_token AND CART_STATUS IN ('ACTIVE', 'CHECKOUT')
            ORDER BY CART_ID DESC
            """,
            {'guest_token': guest_token},
        )
    else:
        return None
    if not rows:
        return None
    return _fetch_cart(int(rows[0]['cart_id']))


def _create_cart(*, user_id: Optional[int], guest_token: Optional[str], location_code: int) -> Dict[str, Any]:
    cart_id = _next_id('SEQ_MH_CART_ID')
    token = guest_token or (str(uuid.uuid4()) if user_id is None else None)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO MH_CART (
                    CART_ID, USER_ID, GUEST_TOKEN, LOCATION_CODE, CART_STATUS, CURRENCY_CODE, CREATED_AT
                ) VALUES (
                    :cart_id, :user_id, :guest_token, :location_code, 'ACTIVE', 'QAR', SYSTIMESTAMP
                )
                """,
                {
                    'cart_id': cart_id,
                    'user_id': user_id,
                    'guest_token': token,
                    'location_code': int(location_code),
                },
            )
        conn.commit()
    cart = _fetch_cart(cart_id)
    assert cart is not None
    return cart


def get_cart(
    *,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
    location_code: Optional[int] = None,
) -> Dict[str, Any]:
    if not _cart_ready():
        return _build_response({
            'cart_id': 0,
            'guest_token': guest_token or str(uuid.uuid4()),
            'location_code': resolve_location_code(location_code),
            'cart_status': 'ACTIVE',
            'currency_code': 'QAR',
            'items': [],
        })
    # Guest browsing without a cart token — return empty shell (cart is created on first add).
    if user_id is None and not guest_token:
        return _build_response({
            'cart_id': 0,
            'guest_token': None,
            'location_code': resolve_location_code(location_code),
            'cart_status': 'ACTIVE',
            'currency_code': 'QAR',
            'items': [],
        })
    cart = _find_active_cart(user_id=user_id, guest_token=guest_token)
    if not cart:
        cart = _create_cart(
            user_id=user_id,
            guest_token=guest_token,
            location_code=resolve_location_code(location_code),
        )
    return _build_response(cart)


def get_active_cart_id(*, user_id: int) -> Optional[int]:
    if not _cart_ready():
        return None
    rows = _safe_rows(
        """
        SELECT CART_ID AS cart_id FROM MH_CART
        WHERE USER_ID = :user_id AND CART_STATUS IN ('ACTIVE', 'CHECKOUT')
        ORDER BY CART_ID DESC
        FETCH FIRST 1 ROWS ONLY
        """,
        {'user_id': int(user_id)},
    )
    return int(rows[0]['cart_id']) if rows else None


def get_cart_for_checkout(*, cart_id: int) -> Dict[str, Any]:
    """Cart lines + totals for order confirm — skips ITEMMASTER lookups."""
    cart = _fetch_cart(int(cart_id))
    if not cart:
        raise ValueError('Cart not found')
    return _build_response(cart, include_product_meta=True)


def _fetch_cart_with_cursor(cur: Any, cart_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT
            CART_ID, USER_ID, GUEST_TOKEN, LOCATION_CODE, CART_STATUS, CURRENCY_CODE
        FROM MH_CART
        WHERE CART_ID = :cart_id
        """,
        {'cart_id': int(cart_id)},
    )
    header = cur.fetchone()
    if not header:
        return None
    cart = {
        'cart_id': int(header[0]),
        'user_id': header[1],
        'guest_token': header[2],
        'location_code': int(header[3] or 1),
        'cart_status': header[4] or 'ACTIVE',
        'currency_code': header[5] or 'QAR',
    }
    cur.execute(
        _cart_item_select_sql(),
        {'cart_id': int(cart_id)},
    )
    items = []
    for row in cur.fetchall():
        items.append({
            'cart_item_id': int(row[0]),
            'item_code': int(row[1]),
            'location_code': int(row[2]),
            'quantity': float(row[3] or 0),
            'unit_price': float(row[4] or 0),
            'line_status': row[5] or 'ACTIVE',
            'parent_item_code': _parent_int(row[6] if len(row) > 6 else None),
        })
    cart['items'] = items
    return cart


def add_item(
    *,
    item_code: int,
    quantity: float,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
    location_code: Optional[int] = None,
    parent_item_code: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _cart_ready():
        return False, 'Cart tables not available', None
    if quantity <= 0:
        return False, 'Quantity must be positive', None
    if web_meta_svc.is_hidden_from_web(int(item_code)) and not web_meta_svc.is_addon_item(int(item_code)):
        return False, 'Product is not available', None
    loc = resolve_location_code(location_code)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT NVL(RETAILPRICE, 0), NVL(WHOLESALEPRICE, 0)
                    FROM ITEMMASTER
                    WHERE ITEMCODE = :item_code
                      AND LOCATIONCODE = :location_code
                      AND ROWNUM = 1
                    """,
                    {'item_code': int(item_code), 'location_code': int(loc)},
                )
                price_row = cur.fetchone()
                if not price_row:
                    return False, 'Product not found', None
                retail = _float_price(price_row[0])
                wholesale = _float_price(price_row[1])
                resolved_offer = web_meta_svc.resolve_offer_price(
                    int(item_code),
                    wholesale_price=wholesale,
                )
                if resolved_offer is not None:
                    wholesale = resolved_offer
                unit_price = effective_unit_price(retail, wholesale)

                cart_id: Optional[int] = None
                guest_token_out = guest_token
                if user_id is not None:
                    cur.execute(
                        """
                        SELECT CART_ID, GUEST_TOKEN
                        FROM (
                            SELECT CART_ID, GUEST_TOKEN
                            FROM MH_CART
                            WHERE USER_ID = :user_id AND CART_STATUS IN ('ACTIVE', 'CHECKOUT')
                            ORDER BY CART_ID DESC
                        )
                        WHERE ROWNUM = 1
                        """,
                        {'user_id': int(user_id)},
                    )
                    cart_row = cur.fetchone()
                elif guest_token:
                    cur.execute(
                        """
                        SELECT CART_ID, GUEST_TOKEN
                        FROM (
                            SELECT CART_ID, GUEST_TOKEN
                            FROM MH_CART
                            WHERE GUEST_TOKEN = :guest_token AND CART_STATUS IN ('ACTIVE', 'CHECKOUT')
                            ORDER BY CART_ID DESC
                        )
                        WHERE ROWNUM = 1
                        """,
                        {'guest_token': guest_token},
                    )
                    cart_row = cur.fetchone()
                else:
                    cart_row = None
                if cart_row:
                    cart_id = int(cart_row[0])
                    if cart_row[1]:
                        guest_token_out = str(cart_row[1])
                else:
                    cur.execute('SELECT SEQ_MH_CART_ID.NEXTVAL FROM DUAL')
                    cart_id = int((cur.fetchone() or [0])[0])
                    guest_token_out = guest_token or str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO MH_CART (
                            CART_ID, USER_ID, GUEST_TOKEN, LOCATION_CODE, CART_STATUS, CURRENCY_CODE, CREATED_AT
                        ) VALUES (
                            :cart_id, :user_id, :guest_token, :location_code, 'ACTIVE', 'QAR', SYSTIMESTAMP
                        )
                        """,
                        {
                            'cart_id': cart_id,
                            'user_id': user_id,
                            'guest_token': guest_token_out,
                            'location_code': int(loc),
                        },
                    )

                assert cart_id is not None
                parent = _parent_int(parent_item_code)
                if _has_parent_column():
                    cur.execute(
                        """
                        SELECT CART_ITEM_ID, QUANTITY
                        FROM MH_CART_ITEM
                        WHERE CART_ID = :cart_id AND ITEM_CODE = :item_code AND LOCATION_CODE = :loc
                          AND LINE_STATUS = 'ACTIVE'
                          AND NVL(PARENT_ITEM_CODE, 0) = :parent
                        """,
                        {
                            'cart_id': cart_id,
                            'item_code': int(item_code),
                            'loc': loc,
                            'parent': int(parent or 0),
                        },
                    )
                else:
                    cur.execute(
                        """
                        SELECT CART_ITEM_ID, QUANTITY
                        FROM MH_CART_ITEM
                        WHERE CART_ID = :cart_id AND ITEM_CODE = :item_code AND LOCATION_CODE = :loc
                          AND LINE_STATUS = 'ACTIVE'
                        """,
                        {'cart_id': cart_id, 'item_code': int(item_code), 'loc': loc},
                    )
                existing = cur.fetchone()
                if existing:
                    new_qty = float(existing[1]) + quantity
                    cur.execute(
                        """
                        UPDATE MH_CART_ITEM
                        SET QUANTITY = :qty, UNIT_PRICE = :price, MODIFIED_AT = SYSTIMESTAMP
                        WHERE CART_ITEM_ID = :cart_item_id
                        """,
                        {
                            'qty': new_qty,
                            'price': unit_price,
                            'cart_item_id': int(existing[0]),
                        },
                    )
                else:
                    cur.execute('SELECT SEQ_MH_CART_ITEM_ID.NEXTVAL FROM DUAL')
                    item_id = int((cur.fetchone() or [0])[0])
                    if _has_parent_column():
                        cur.execute(
                            """
                            INSERT INTO MH_CART_ITEM (
                                CART_ITEM_ID, CART_ID, LOCATION_CODE, ITEM_CODE,
                                QUANTITY, UNIT_PRICE, LINE_STATUS, CREATED_AT, PARENT_ITEM_CODE
                            ) VALUES (
                                :item_id, :cart_id, :loc, :item_code,
                                :qty, :price, 'ACTIVE', SYSTIMESTAMP, :parent
                            )
                            """,
                            {
                                'item_id': item_id,
                                'cart_id': cart_id,
                                'loc': loc,
                                'item_code': int(item_code),
                                'qty': quantity,
                                'price': unit_price,
                                'parent': parent,
                            },
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO MH_CART_ITEM (
                                CART_ITEM_ID, CART_ID, LOCATION_CODE, ITEM_CODE,
                                QUANTITY, UNIT_PRICE, LINE_STATUS, CREATED_AT
                            ) VALUES (
                                :item_id, :cart_id, :loc, :item_code,
                                :qty, :price, 'ACTIVE', SYSTIMESTAMP
                            )
                            """,
                            {
                                'item_id': item_id,
                                'cart_id': cart_id,
                                'loc': loc,
                                'item_code': int(item_code),
                                'qty': quantity,
                                'price': unit_price,
                            },
                        )

                updated = _fetch_cart_with_cursor(cur, cart_id)
                discount_total = 0.0
                try:
                    cur.execute(
                        """
                        SELECT NVL(SUM(DISCOUNT_AMOUNT), 0)
                        FROM MH_CART_COUPON
                        WHERE CART_ID = :cart_id
                        """,
                        {'cart_id': int(cart_id)},
                    )
                    discount_row = cur.fetchone()
                    if discount_row is not None:
                        discount_total = float(discount_row[0] or 0)
                except Exception:
                    discount_total = 0.0
            conn.commit()
        if not updated:
            return False, 'Cart not found after update', None
        if guest_token_out and not guest_token:
            updated['guest_token'] = guest_token_out
        return True, 'Item added to cart', _build_response(
            updated, discount_total=discount_total, include_product_meta=True
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def update_item_quantity(
    *,
    cart_item_id: int,
    quantity: float,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _cart_ready():
        return False, 'Cart tables not available', None
    cart = _find_active_cart(user_id=user_id, guest_token=guest_token)
    if not cart:
        return False, 'Cart not found', None
    if quantity <= 0:
        return remove_item(cart_item_id=cart_item_id, user_id=user_id, guest_token=guest_token)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                parent_code = None
                line_item_code = None
                if _has_parent_column():
                    cur.execute(
                        """
                        SELECT ITEM_CODE, PARENT_ITEM_CODE
                        FROM MH_CART_ITEM
                        WHERE CART_ITEM_ID = :cart_item_id AND CART_ID = :cart_id
                        """,
                        {
                            'cart_item_id': int(cart_item_id),
                            'cart_id': int(cart['cart_id']),
                        },
                    )
                    line_row = cur.fetchone()
                    if line_row:
                        line_item_code = int(line_row[0])
                        parent_code = _parent_int(line_row[1])
                cur.execute(
                    """
                    UPDATE MH_CART_ITEM
                    SET QUANTITY = :qty, MODIFIED_AT = SYSTIMESTAMP
                    WHERE CART_ITEM_ID = :cart_item_id AND CART_ID = :cart_id
                    """,
                    {
                        'qty': quantity,
                        'cart_item_id': int(cart_item_id),
                        'cart_id': int(cart['cart_id']),
                    },
                )
                if _has_parent_column() and line_item_code and not parent_code:
                    cur.execute(
                        """
                        UPDATE MH_CART_ITEM
                        SET QUANTITY = :qty, MODIFIED_AT = SYSTIMESTAMP
                        WHERE CART_ID = :cart_id
                          AND PARENT_ITEM_CODE = :parent
                          AND LINE_STATUS = 'ACTIVE'
                        """,
                        {
                            'qty': quantity,
                            'cart_id': int(cart['cart_id']),
                            'parent': int(line_item_code),
                        },
                    )
            conn.commit()
        updated = _fetch_cart(int(cart['cart_id']))
        return True, 'Cart item updated', _build_response(updated or cart, include_product_meta=True)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def remove_item(
    *,
    cart_item_id: int,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _cart_ready():
        return False, 'Cart tables not available', None
    cart = _find_active_cart(user_id=user_id, guest_token=guest_token)
    if not cart:
        return False, 'Cart not found', None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if _has_parent_column():
                    cur.execute(
                        """
                        SELECT ITEM_CODE, PARENT_ITEM_CODE
                        FROM MH_CART_ITEM
                        WHERE CART_ITEM_ID = :cart_item_id AND CART_ID = :cart_id
                        """,
                        {
                            'cart_item_id': int(cart_item_id),
                            'cart_id': int(cart['cart_id']),
                        },
                    )
                    line_row = cur.fetchone()
                    if line_row and not _parent_int(line_row[1]):
                        cur.execute(
                            """
                            DELETE FROM MH_CART_ITEM
                            WHERE CART_ID = :cart_id AND PARENT_ITEM_CODE = :parent
                            """,
                            {
                                'cart_id': int(cart['cart_id']),
                                'parent': int(line_row[0]),
                            },
                        )
                cur.execute(
                    """
                    DELETE FROM MH_CART_ITEM
                    WHERE CART_ITEM_ID = :cart_item_id AND CART_ID = :cart_id
                    """,
                    {'cart_item_id': int(cart_item_id), 'cart_id': int(cart['cart_id'])},
                )
            conn.commit()
        updated = _fetch_cart(int(cart['cart_id']))
        return True, 'Cart item removed', _build_response(updated or cart, include_product_meta=True)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def set_parent_addon(
    *,
    parent_item_code: int,
    addon_item_code: Optional[int] = None,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
    location_code: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _cart_ready():
        return False, 'Cart tables not available', None
    cart = _find_active_cart(user_id=user_id, guest_token=guest_token)
    if not cart:
        return False, 'Add the product to the cart first', None

    parent = int(parent_item_code)
    parent_line = None
    for item in cart.get('items') or []:
        if int(item.get('item_code') or 0) != parent:
            continue
        if _parent_int(item.get('parent_item_code')):
            continue
        parent_line = item
        break
    if not parent_line:
        return False, 'Add the product to the cart first', None

    qty = float(parent_line.get('quantity') or 1)
    if qty <= 0:
        qty = 1.0

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if _has_parent_column():
                    cur.execute(
                        """
                        DELETE FROM MH_CART_ITEM
                        WHERE CART_ID = :cart_id AND PARENT_ITEM_CODE = :parent
                        """,
                        {'cart_id': int(cart['cart_id']), 'parent': parent},
                    )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None

    if not addon_item_code:
        updated = _fetch_cart(int(cart['cart_id']))
        return True, 'Gift wrap removed', _build_response(
            updated or cart, include_product_meta=True
        )

    return add_item(
        item_code=int(addon_item_code),
        quantity=qty,
        user_id=user_id,
        guest_token=guest_token,
        location_code=location_code,
        parent_item_code=parent,
    )


def apply_coupon(
    *,
    coupon_code: str,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _coupons_enabled():
        return False, 'Coupons are not enabled for this store', None
    if not _cart_ready():
        return False, 'Cart tables not available', None
    cart_data = get_cart(user_id=user_id, guest_token=guest_token)
    if not cart_data.get('items'):
        return False, 'Cart is empty', None
    subtotal = float(cart_data['summary']['subtotal'])
    try:
        promo = promo_svc.validate_coupon(coupon_code, user_id=user_id, subtotal=subtotal)
    except ValueError as exc:
        return False, str(exc), None

    cart_id = int(cart_data['cart_id'])
    if cart_id <= 0:
        return False, 'Cart not found', None

    if _table_exists('MH_CART_COUPON'):
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        'DELETE FROM MH_CART_COUPON WHERE CART_ID = :cart_id',
                        {'cart_id': cart_id},
                    )
                    cur.execute('SELECT SEQ_MH_CART_COUPON_ID.NEXTVAL AS id FROM DUAL')
                    coupon_row_id = int((cur.fetchone() or [0])[0])
                    cur.execute(
                        """
                        INSERT INTO MH_CART_COUPON (
                            CART_COUPON_ID, CART_ID, COUPON_CODE, DISCOUNT_AMOUNT,
                            APPLIED_AT, CREATED_AT
                        ) VALUES (
                            :id, :cart_id, :coupon_code, :discount, SYSTIMESTAMP, SYSTIMESTAMP
                        )
                        """,
                        {
                            'id': coupon_row_id,
                            'cart_id': cart_id,
                            'coupon_code': promo['coupon_code'],
                            'discount': promo['discount_amount'],
                        },
                    )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            return False, str(exc), None

    updated = get_cart(user_id=user_id, guest_token=guest_token)
    return True, 'Coupon applied', {'cart': updated, 'coupon': promo}
