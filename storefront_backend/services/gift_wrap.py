"""Gift wrap add-on items for the product details page."""
from __future__ import annotations

from typing import Any, Optional

from db import _get_connection, _safe_rows

from addons.ecommerce.services import product_web_meta as web_meta_svc
from storefront_backend.deps import default_location_code

ADDON_TYPE = 'gift_wrap'
NOTE_PREFIX = 'Gift wrap:'

WRAP_SPECS: tuple[dict[str, Any], ...] = (
    {
        'code': 'free',
        'label': 'Free Gift Wrap',
        'label_ar': 'تغليف هدية مجاني',
        'fee': 0.0,
        'sort': 10,
    },
    {
        'code': 'classic-boys',
        'label': 'Classic Gift Wrap for Boys',
        'label_ar': 'تغليف كلاسيكي للأولاد',
        'fee': 8.0,
        'sort': 20,
    },
    {
        'code': 'classic-girls',
        'label': 'Classic Gift Wrap for Girls',
        'label_ar': 'تغليف كلاسيكي للبنات',
        'fee': 8.0,
        'sort': 30,
    },
    {
        'code': 'premium-boys',
        'label': 'Premium Gift Wrap for Boys',
        'label_ar': 'تغليف فاخر للأولاد',
        'fee': 16.0,
        'sort': 40,
    },
    {
        'code': 'premium-girls',
        'label': 'Premium Gift Wrap for Girls',
        'label_ar': 'تغليف فاخر للبنات',
        'fee': 16.0,
        'sort': 50,
    },
    {
        'code': 'newborn',
        'label': 'Newborn Gift Wrap',
        'label_ar': 'تغليف حديثي الولادة',
        'fee': 16.0,
        'sort': 60,
    },
    {
        'code': 'birthday',
        'label': 'Birthday Gift Wrap',
        'label_ar': 'تغليف عيد الميلاد',
        'fee': 16.0,
        'sort': 70,
    },
)

_ENSURED = False


def _location_code() -> int:
    return default_location_code()


def _existing_by_name(location_code: int) -> dict[str, int]:
    rows = _safe_rows(
        """
        SELECT ITEMCODE AS item_code, ITEMNAME AS item_name
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :loc
          AND UPPER(ITEMNAME) IN (
            'FREE GIFT WRAP',
            'CLASSIC GIFT WRAP FOR BOYS',
            'CLASSIC GIFT WRAP FOR GIRLS',
            'PREMIUM GIFT WRAP FOR BOYS',
            'PREMIUM GIFT WRAP FOR GIRLS',
            'NEWBORN GIFT WRAP',
            'BIRTHDAY GIFT WRAP'
          )
        """,
        {'loc': int(location_code)},
    )
    out: dict[str, int] = {}
    for row in rows or []:
        name = str(row.get('item_name') or '').strip().upper()
        try:
            out[name] = int(row['item_code'])
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _next_item_code(location_code: int) -> int:
    rows = _safe_rows(
        """
        SELECT NVL(MAX(ITEMCODE), 0) AS max_code
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :loc
        """,
        {'loc': int(location_code)},
    )
    current = int((rows[0] or {}).get('max_code') or 0) if rows else 0
    return max(current + 1, 900001)


def _insert_item(location_code: int, item_code: int, spec: dict[str, Any]) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ITEMMASTER (
                    LOCATIONCODE, ITEMCODE, CATEGORYCODE, ITEMNAME, MANUFACTURERID,
                    BRANDCODE, SIZECODE, COLORCODE, BASEUOM,
                    COSTPRICE, RETAILPRICE, WHOLESALEPRICE, THIRDPRICE, BRANCHPRICE,
                    MAXIMUMLEVEL, REORDERLEVEL, CURRENTSTOCK, DISCOUNTFLAG,
                    COMPANYCODE, SUPCODE, DEPARTMENTCODE,
                    MAINCATEGORY, REBATE, ITEMNAMEARA, DESCRIPTION,
                    PROPERTY, ORIGIN, QUANTITYLIMIT, PACKING,
                    MINISTRYFACTOR, MINISTRYUNIT, VATPERCENT,
                    SALESACCOUNT, PURCHASEACCOUNT, INVENTORYACCOUNT, COGSACCOUNT,
                    ITEMFLAG, CREATIONFLAG
                ) VALUES (
                    :loc, :item_code, 0, :item_name, :manufacturer_id,
                    0, 0, 0, 'PC',
                    0, :retail_price, 0, 0, 0,
                    0, 0, 9999, 'N',
                    '', 0, 0,
                    0, 0, :item_name_ar, :description,
                    0, 0, 0, '',
                    '', '', 0,
                    '', '', '', '',
                    'Y', 'B'
                )
                """,
                {
                    'loc': int(location_code),
                    'item_code': int(item_code),
                    'item_name': str(spec['label'])[:200],
                    'item_name_ar': str(spec['label_ar'])[:200],
                    'description': 'Gift wrapping add-on',
                    'manufacturer_id': f'GW{int(item_code):010d}',
                    'retail_price': float(spec['fee']),
                },
            )
        conn.commit()


def _sync_existing_item(location_code: int, item_code: int, spec: dict[str, Any]) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ITEMMASTER
                SET ITEMNAME = :item_name,
                    ITEMNAMEARA = :item_name_ar,
                    RETAILPRICE = :retail_price,
                    CURRENTSTOCK = 9999
                WHERE LOCATIONCODE = :loc AND ITEMCODE = :item_code
                """,
                {
                    'loc': int(location_code),
                    'item_code': int(item_code),
                    'item_name': str(spec['label'])[:200],
                    'item_name_ar': str(spec['label_ar'])[:200],
                    'retail_price': float(spec['fee']),
                },
            )
        conn.commit()


def _flag_addon(item_code: int, spec: dict[str, Any]) -> None:
    web_meta_svc.save_product_web_meta(
        int(item_code),
        show_on_web=False,
        is_featured=False,
        is_addon=True,
        addon_type=ADDON_TYPE,
        addon_sort=int(spec['sort']),
        addon_code=str(spec.get('code') or ''),
        touch_web_flags=True,
    )


def ensure_addon_items() -> list[int]:
    """Create missing gift-wrap SKUs and mark them as hidden add-on items."""
    global _ENSURED
    if _ENSURED:
        return []
    location_code = _location_code()
    existing = _existing_by_name(location_code)
    created_or_found: list[int] = []
    next_code = _next_item_code(location_code)

    for spec in WRAP_SPECS:
        key = str(spec['label']).upper()
        item_code = existing.get(key)
        if item_code is None:
            while True:
                clash = _safe_rows(
                    """
                    SELECT ITEMCODE AS item_code
                    FROM ITEMMASTER
                    WHERE LOCATIONCODE = :loc AND ITEMCODE = :item_code
                    """,
                    {'loc': int(location_code), 'item_code': int(next_code)},
                )
                if not clash:
                    break
                next_code += 1
            item_code = next_code
            _insert_item(location_code, item_code, spec)
            next_code += 1
        else:
            _sync_existing_item(location_code, item_code, spec)
        _flag_addon(int(item_code), spec)
        created_or_found.append(int(item_code))

    _ENSURED = True
    return created_or_found


def is_free_wrap(
    item: Optional[dict[str, Any]] = None,
    *,
    item_code: Optional[int] = None,
    meta_map: Optional[dict[str, Any]] = None,
) -> bool:
    mapping = meta_map if meta_map is not None else web_meta_svc.product_web_meta_map()
    code = 0
    name = ''
    if item:
        try:
            code = int(item.get('item_code') or 0)
        except (TypeError, ValueError):
            code = 0
        name = str(item.get('item_name') or '').strip().lower()
        addon_code = str(item.get('addon_code') or '').strip().lower()
        if addon_code == 'free' or name == 'free gift wrap':
            return True
    if item_code is not None:
        code = int(item_code)
    if not code:
        return False
    meta = (mapping or {}).get(str(code))
    if web_meta_svc.addon_code_from_meta(meta) == 'free':
        return True
    if name == 'free gift wrap':
        return True
    return False


def addon_is_enabled(
    item: Optional[dict[str, Any]] = None,
    *,
    item_code: Optional[int] = None,
    meta_map: Optional[dict[str, Any]] = None,
) -> bool:
    from addons.ecommerce import settings_store

    if not settings_store.free_gift_wrap_enabled():
        return True
    return is_free_wrap(item, item_code=item_code, meta_map=meta_map)


def split_notes(notes: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    text = (notes or '').strip()
    if not text:
        return None, None
    first, _sep, rest = text.partition('\n')
    if not first.lower().startswith(NOTE_PREFIX.lower()):
        return None, text
    body = first[len(NOTE_PREFIX) :].strip()
    fee = 0.0
    label = body
    if '(+' in body and 'QAR)' in body:
        name, _plus, amount = body.rpartition('(+')
        label = name.strip()
        digits = ''.join(ch for ch in amount if ch.isdigit() or ch == '.')
        if digits:
            fee = float(digits)
    return {'label': label, 'fee': fee}, (rest.strip() or None)
