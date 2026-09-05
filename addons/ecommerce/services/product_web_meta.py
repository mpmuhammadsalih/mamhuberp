"""Ecommerce-only product fields stored in MH_MEDIA (product_detail placement)."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import media_db

_PLACEMENT = 'product_detail'
_PLACEHOLDER_IMAGE = '/media/files/product-detail-placeholder.svg'


def _parse_offer(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed if parsed > 0 else None


def product_web_meta_map() -> Dict[str, Dict[str, Any]]:
    """Map item code -> merged meta from product_detail rows."""
    if not media_db.media_table_ready():
        return {}
    rows, _ = media_db.list_media(placement=_PLACEMENT, active_only=False)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ref = str(row.get('ref_key') or '').strip()
        if not ref:
            continue
        meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
        bucket = out.setdefault(ref, {})
        for key in ('specifications', 'specifications_ar', 'description_ar'):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                bucket[key] = value.strip()
        offer = _parse_offer(meta.get('offer_price'))
        if offer is not None:
            bucket['offer_price'] = offer
    return out


def get_product_detail_row(item_code: int) -> Optional[Dict[str, Any]]:
    if not media_db.media_table_ready():
        return None
    rows, _ = media_db.list_media(placement=_PLACEMENT, active_only=False)
    return next(
        (row for row in rows if str(row.get('ref_key') or '').strip() == str(item_code)),
        None,
    )


def resolve_offer_price(
    item_code: int,
    *,
    wholesale_price: Any = None,
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[float]:
    """Prefer ecommerce meta offer, then ITEMMASTER wholesale price."""
    ref = str(item_code)
    meta = (meta_map or product_web_meta_map()).get(ref) or {}
    meta_offer = _parse_offer(meta.get('offer_price'))
    if meta_offer is not None:
        return meta_offer
    return _parse_offer(wholesale_price)


def save_product_web_meta(
    item_code: int,
    *,
    specifications: Optional[str] = None,
    specifications_ar: Optional[str] = None,
    description_ar: Optional[str] = None,
    offer_price: Optional[str] = None,
    fallback_image: str = '',
    touch_specs: bool = False,
    touch_specs_ar: bool = False,
    touch_description_ar: bool = False,
    touch_offer: bool = False,
) -> Tuple[bool, str]:
    """Merge specifications, Arabic content, and/or offer price into product_detail meta."""
    if not touch_specs and not touch_specs_ar and not touch_description_ar and not touch_offer:
        return (True, '')
    if not media_db.media_table_ready():
        if touch_offer and offer_price is not None:
            return (False, 'Offer price requires the MH_MEDIA table.')
        return (True, '')

    existing = get_product_detail_row(item_code)
    meta: Dict[str, Any] = {}
    if existing and isinstance(existing.get('meta'), dict):
        meta = dict(existing['meta'])

    if touch_specs:
        specs_text = str(specifications or '').strip()
        if specs_text:
            meta['specifications'] = specs_text[:3500]
        else:
            meta.pop('specifications', None)

    if touch_specs_ar:
        specs_ar_text = str(specifications_ar or '').strip()
        if specs_ar_text:
            meta['specifications_ar'] = specs_ar_text[:3500]
        else:
            meta.pop('specifications_ar', None)

    if touch_description_ar:
        desc_ar_text = str(description_ar or '').strip()
        if desc_ar_text:
            meta['description_ar'] = desc_ar_text[:3500]
        else:
            meta.pop('description_ar', None)

    if touch_offer:
        if offer_price is None:
            pass
        else:
            parsed = _parse_offer(offer_price)
            if parsed is None:
                meta.pop('offer_price', None)
            else:
                meta['offer_price'] = parsed

    has_specs = bool(str(meta.get('specifications') or '').strip())
    has_specs_ar = bool(str(meta.get('specifications_ar') or '').strip())
    has_desc_ar = bool(str(meta.get('description_ar') or '').strip())
    has_offer = _parse_offer(meta.get('offer_price')) is not None
    if not has_specs and not has_specs_ar and not has_desc_ar and not has_offer:
        if existing and existing.get('media_id'):
            media_db.deactivate_media(int(existing['media_id']))
        return (True, '')

    image_url = str(existing.get('image_url') if existing else fallback_image or '').strip()
    if not image_url:
        image_url = _PLACEHOLDER_IMAGE

    payload = {
        'media_id': existing.get('media_id') if existing else None,
        'placement': _PLACEMENT,
        'ref_key': str(item_code),
        'title': f'Product {item_code} web details',
        'subtitle': None,
        'image_url': image_url,
        'link_url': None,
        'alt_text': f'Product {item_code} web details',
        'sort_order': 0,
        'is_active': True,
        'meta': meta,
    }
    ok, msg, _ = media_db.upsert_media(payload)
    return (ok, msg if not ok else '')
