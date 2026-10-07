"""Wishlist via MH_WISHLIST tables."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists

from storefront_backend.deps import resolve_location_code
from storefront_backend.services import cart as cart_svc
from storefront_backend.services import catalog as catalog_svc
from storefront_backend.services.schema_bootstrap import ensure_wishlist_schema


def _ready() -> bool:
    ensure_wishlist_schema()
    return _table_exists('MH_WISHLIST') and _table_exists('MH_WISHLIST_ITEM')


def _next_id(sequence: str) -> int:
    rows = _safe_rows(f'SELECT {sequence}.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _fetch_wishlist(wishlist_id: int) -> Optional[Dict[str, Any]]:
    headers = _safe_rows(
        """
        SELECT
            WISHLIST_ID AS wishlist_id,
            WISHLIST_NAME AS wishlist_name,
            IS_DEFAULT AS is_default
        FROM MH_WISHLIST
        WHERE WISHLIST_ID = :wishlist_id
        """,
        {'wishlist_id': int(wishlist_id)},
    )
    if not headers:
        return None
    wishlist = dict(headers[0])
    wishlist['items'] = _safe_rows(
        """
        SELECT
            WISHLIST_ITEM_ID AS wishlist_item_id,
            ITEM_CODE AS item_code,
            LOCATION_CODE AS location_code
        FROM MH_WISHLIST_ITEM
        WHERE WISHLIST_ID = :wishlist_id
        ORDER BY WISHLIST_ITEM_ID
        """,
        {'wishlist_id': int(wishlist_id)},
    )
    return wishlist


def _get_default_wishlist_id(user_id: int) -> Optional[int]:
    rows = _safe_rows(
        """
        SELECT WISHLIST_ID AS wishlist_id
        FROM MH_WISHLIST
        WHERE USER_ID = :user_id AND IS_DEFAULT = 1
        ORDER BY WISHLIST_ID DESC
        """,
        {'user_id': int(user_id)},
    )
    return int(rows[0]['wishlist_id']) if rows else None


def _get_or_create_default(user_id: int) -> Dict[str, Any]:
    if not _ready():
        return {
            'wishlist_id': 0,
            'wishlist_name': 'My Wishlist',
            'is_default': True,
            'items': [],
        }
    wishlist_id = _get_default_wishlist_id(user_id)
    if wishlist_id is None:
        wishlist_id = _next_id('SEQ_MH_WISHLIST_ID')
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO MH_WISHLIST (
                        WISHLIST_ID, USER_ID, WISHLIST_NAME, IS_DEFAULT, CREATED_AT, CREATED_BY
                    ) VALUES (
                        :wishlist_id, :user_id, 'My Wishlist', 1, SYSTIMESTAMP, :created_by
                    )
                    """,
                    {
                        'wishlist_id': wishlist_id,
                        'user_id': int(user_id),
                        'created_by': int(user_id),
                    },
                )
            conn.commit()
    fetched = _fetch_wishlist(wishlist_id)
    assert fetched is not None
    return fetched


def _build_response(wishlist: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for item in wishlist.get('items') or []:
        loc = int(item['location_code'])
        code = int(item['item_code'])
        product = catalog_svc.get_product(code, location_code=loc) or {'item_code': code}
        items.append({
            'wishlist_item_id': int(item['wishlist_item_id']),
            'item_code': code,
            'location_code': loc,
            'product': product,
        })
    return {
        'wishlist_id': int(wishlist['wishlist_id']),
        'wishlist_name': wishlist.get('wishlist_name') or 'My Wishlist',
        'is_default': int(wishlist.get('is_default') or 0) == 1,
        'items': items,
    }


def get_wishlist(user_id: int) -> Dict[str, Any]:
    wishlist = _get_or_create_default(user_id)
    return _build_response(wishlist)


def add_item(
    user_id: int,
    *,
    item_code: int,
    location_code: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Wishlist tables not available', None
    loc = resolve_location_code(location_code)
    product = catalog_svc.get_product(int(item_code), location_code=loc)
    if not product:
        return False, 'Product not found', None

    wishlist = _get_or_create_default(user_id)
    wishlist_id = int(wishlist['wishlist_id'])
    existing = _safe_rows(
        """
        SELECT WISHLIST_ITEM_ID AS wishlist_item_id
        FROM MH_WISHLIST_ITEM
        WHERE WISHLIST_ID = :wishlist_id
          AND LOCATION_CODE = :loc
          AND ITEM_CODE = :item_code
        """,
        {'wishlist_id': wishlist_id, 'loc': loc, 'item_code': int(item_code)},
    )
    if not existing:
        item_id = _next_id('SEQ_MH_WISHLIST_ITEM_ID')
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO MH_WISHLIST_ITEM (
                            WISHLIST_ITEM_ID, WISHLIST_ID, LOCATION_CODE, ITEM_CODE,
                            CREATED_AT, CREATED_BY
                        ) VALUES (
                            :item_id, :wishlist_id, :loc, :item_code,
                            SYSTIMESTAMP, :created_by
                        )
                        """,
                        {
                            'item_id': item_id,
                            'wishlist_id': wishlist_id,
                            'loc': loc,
                            'item_code': int(item_code),
                            'created_by': int(user_id),
                        },
                    )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            return False, str(exc), None

    updated = _fetch_wishlist(wishlist_id)
    return True, 'Item added to wishlist', _build_response(updated or wishlist)


def remove_item(user_id: int, wishlist_item_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Wishlist tables not available', None
    wishlist = _get_or_create_default(user_id)
    wishlist_id = int(wishlist['wishlist_id'])
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM MH_WISHLIST_ITEM
                    WHERE WISHLIST_ITEM_ID = :item_id AND WISHLIST_ID = :wishlist_id
                    """,
                    {'item_id': int(wishlist_item_id), 'wishlist_id': wishlist_id},
                )
                if cur.rowcount == 0:
                    return False, 'Wishlist item not found', None
            conn.commit()
        updated = _fetch_wishlist(wishlist_id)
        return True, 'Wishlist item removed', _build_response(updated or wishlist)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def move_to_cart(
    user_id: int,
    wishlist_item_id: int,
) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Wishlist tables not available', None, None
    wishlist = _get_or_create_default(user_id)
    item = next(
        (i for i in wishlist.get('items') or [] if int(i['wishlist_item_id']) == int(wishlist_item_id)),
        None,
    )
    if not item:
        return False, 'Wishlist item not found', None, None

    ok, message, cart = cart_svc.add_item(
        item_code=int(item['item_code']),
        quantity=1,
        user_id=user_id,
        location_code=int(item['location_code']),
    )
    if not ok or not cart:
        return False, message, None, None

    ok2, msg2, wishlist_data = remove_item(user_id, wishlist_item_id)
    if not ok2 or not wishlist_data:
        return False, msg2, None, cart
    return True, 'Item moved to cart', wishlist_data, cart
