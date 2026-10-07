"""Ecommerce-only product fields stored in MH_MEDIA (product_detail placement)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce import media_db

_PLACEMENT = 'product_detail'
_PLACEHOLDER_IMAGE = '/media/files/product-detail-placeholder.svg'
_STORE_NAME = 'MamaHub'
_SEO_TITLE_MAX = 70
_SEO_DESC_MAX = 160
_IMPORT_PAGE_URL_MAX = 500


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()


def _clean_import_page_url(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    if text.startswith('//'):
        text = f'https:{text}'
    lower = text.lower()
    if not (lower.startswith('http://') or lower.startswith('https://')):
        text = f'https://{text}'
    return text[:_IMPORT_PAGE_URL_MAX]


_MAX_COMPARE_URLS = 8
_COMPARE_STORE_NAME_MAX = 80


def _clean_store_name(value: Any) -> str:
    return _clean_text(value)[:_COMPARE_STORE_NAME_MAX]


def _as_store_id(value: Any) -> Optional[int]:
    try:
        store_id = int(value or 0)
    except (TypeError, ValueError):
        return None
    return store_id if store_id > 0 else None


def clean_compare_urls(value: Any) -> List[Dict[str, Any]]:
    raw_items: List[Any] = []
    if isinstance(value, list):
        raw_items = list(value)
    elif value:
        raw_items = re.split(r'[\r\n,]+', str(value))
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_items:
        store_id = None
        if isinstance(item, dict):
            url = _clean_import_page_url(item.get('url') or item.get('page_url'))
            name = _clean_store_name(item.get('store_name') or item.get('name'))
            store_id = _as_store_id(item.get('store_id'))
        else:
            url = _clean_import_page_url(item)
            name = ''
        key = url.rstrip('/').lower()
        if not url or key in seen:
            continue
        seen.add(key)
        out.append({'url': url, 'store_name': name, 'store_id': store_id})
        if len(out) >= _MAX_COMPARE_URLS:
            break
    return out


def compare_entries_from_form(
    urls: Any,
    store_ids: Any = None,
    store_names: Any = None,
) -> List[Dict[str, Any]]:
    from addons.ecommerce import compare_stores_db

    url_list = [str(item or '') for item in (urls or [])]
    id_list = list(store_ids or [])
    name_list = [str(item or '') for item in (store_names or [])]
    stores = {
        int(row['store_id']): row
        for row in compare_stores_db.list_compare_stores(active_only=True)
        if row.get('store_id')
    }
    paired: List[Dict[str, Any]] = []
    for index, url in enumerate(url_list):
        store_id = _as_store_id(id_list[index] if index < len(id_list) else None)
        name = ''
        if store_id and store_id in stores:
            name = _clean_store_name(stores[store_id].get('store_name'))
        elif index < len(name_list):
            name = _clean_store_name(name_list[index])
            if not store_id:
                store_id = compare_stores_db.find_store_id_by_name(name)
        paired.append({'url': url, 'store_name': name, 'store_id': store_id})
    return clean_compare_urls(paired)


def auto_seo_title(item_name: str) -> str:
    """Always end with | MamaHub. Trim the product name if the title would exceed 70 characters."""
    name = _clean_text(item_name)
    suffix = f' | {_STORE_NAME}'
    if not name:
        return f'{_STORE_NAME} — toys and gifts in Qatar'[:_SEO_TITLE_MAX]
    if '|' in name:
        name = _clean_text(name.split('|')[0])
    name = re.sub(r'(?i)\s*(?:[|–—-]\s*)?mamahub\s*$', '', name).strip()
    room = _SEO_TITLE_MAX - len(suffix)
    if len(name) > room:
        name = name[: max(0, room - 1)].rstrip() + '…'
    if not name:
        return _STORE_NAME[:_SEO_TITLE_MAX]
    return f'{name}{suffix}'[:_SEO_TITLE_MAX]


def auto_seo_description(
    *,
    item_name: str = '',
    description: str = '',
    category_name: str = '',
    price: Any = None,
) -> str:
    text = _clean_text(description)
    if text:
        return text[:_SEO_DESC_MAX]
    name = _clean_text(item_name) or 'this item'
    category = _clean_text(category_name)
    bits = [f'Buy {name} online at {_STORE_NAME}.']
    if category:
        bits.append(f'Shop {category} toys and gifts delivered in Qatar.')
    else:
        bits.append('Toys and gifts for children, delivered in Qatar.')
    try:
        amount = float(price or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount > 0:
        bits.append(f'From QAR {amount:.2f}.')
    return ' '.join(bits)[:_SEO_DESC_MAX]


def resolve_listing_seo(
    *,
    item_name: str = '',
    description: str = '',
    category_name: str = '',
    price: Any = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    bucket = meta if isinstance(meta, dict) else {}
    custom_title = _clean_text(bucket.get('seo_title'))
    custom_desc = _clean_text(bucket.get('seo_description'))
    return {
        'seo_title': (custom_title or auto_seo_title(item_name))[:_SEO_TITLE_MAX],
        'seo_description': (
            custom_desc
            or auto_seo_description(
                item_name=item_name,
                description=description,
                category_name=category_name,
                price=price,
            )
        )[:_SEO_DESC_MAX],
        'seo_title_custom': custom_title[:_SEO_TITLE_MAX],
        'seo_description_custom': custom_desc[:_SEO_DESC_MAX],
    }


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def show_on_web_from_meta(meta: Optional[Dict[str, Any]]) -> bool:
    bucket = meta if isinstance(meta, dict) else {}
    if 'show_on_web' not in bucket:
        return True
    return _as_bool(bucket.get('show_on_web'), True)


def is_featured_from_meta(meta: Optional[Dict[str, Any]]) -> bool:
    bucket = meta if isinstance(meta, dict) else {}
    return _as_bool(bucket.get('is_featured'), False)


def is_addon_from_meta(meta: Optional[Dict[str, Any]]) -> bool:
    bucket = meta if isinstance(meta, dict) else {}
    return _as_bool(bucket.get('is_addon'), False)


def addon_type_from_meta(meta: Optional[Dict[str, Any]]) -> str:
    bucket = meta if isinstance(meta, dict) else {}
    return str(bucket.get('addon_type') or '').strip().lower()


def addon_code_from_meta(meta: Optional[Dict[str, Any]]) -> str:
    bucket = meta if isinstance(meta, dict) else {}
    return str(bucket.get('addon_code') or '').strip().lower()


def addon_sort_from_meta(meta: Optional[Dict[str, Any]]) -> int:
    bucket = meta if isinstance(meta, dict) else {}
    try:
        return int(bucket.get('addon_sort') or 0)
    except (TypeError, ValueError):
        return 0


def addon_item_codes(
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    addon_type: Optional[str] = None,
) -> List[int]:
    mapping = meta_map if meta_map is not None else product_web_meta_map()
    wanted = (addon_type or '').strip().lower()
    out: List[int] = []
    for ref, meta in (mapping or {}).items():
        if not is_addon_from_meta(meta):
            continue
        if wanted and addon_type_from_meta(meta) not in (wanted, ''):
            continue
        try:
            out.append(int(ref))
        except (TypeError, ValueError):
            continue
    return out


def is_addon_item(
    item_code: int,
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    mapping = meta_map if meta_map is not None else product_web_meta_map()
    return is_addon_from_meta((mapping or {}).get(str(item_code)))


def hidden_item_codes(meta_map: Optional[Dict[str, Dict[str, Any]]] = None) -> List[int]:
    mapping = meta_map if meta_map is not None else product_web_meta_map()
    out: List[int] = []
    for ref, meta in (mapping or {}).items():
        if show_on_web_from_meta(meta):
            continue
        try:
            out.append(int(ref))
        except (TypeError, ValueError):
            continue
    return out


def featured_item_codes(
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    require_visible: bool = True,
) -> List[int]:
    mapping = meta_map if meta_map is not None else product_web_meta_map()
    out: List[int] = []
    for ref, meta in (mapping or {}).items():
        if not is_featured_from_meta(meta):
            continue
        if require_visible and not show_on_web_from_meta(meta):
            continue
        try:
            out.append(int(ref))
        except (TypeError, ValueError):
            continue
    return out


def is_hidden_from_web(
    item_code: int,
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    mapping = meta_map if meta_map is not None else product_web_meta_map()
    return not show_on_web_from_meta((mapping or {}).get(str(item_code)))


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
        for key in (
            'specifications',
            'specifications_ar',
            'description_ar',
            'seo_title',
            'seo_description',
            'import_page_url',
        ):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                bucket[key] = value.strip()
        compare_urls = clean_compare_urls(meta.get('compare_urls'))
        if compare_urls:
            bucket['compare_urls'] = compare_urls
        offer = _parse_offer(meta.get('offer_price'))
        if offer is not None:
            bucket['offer_price'] = offer
        if 'show_on_web' in meta:
            bucket['show_on_web'] = show_on_web_from_meta(meta)
        if is_featured_from_meta(meta):
            bucket['is_featured'] = True
        if is_addon_from_meta(meta):
            bucket['is_addon'] = True
            addon_type = addon_type_from_meta(meta)
            if addon_type:
                bucket['addon_type'] = addon_type
            sort = addon_sort_from_meta(meta)
            if sort:
                bucket['addon_sort'] = sort
            addon_code = addon_code_from_meta(meta)
            if addon_code:
                bucket['addon_code'] = addon_code
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
    seo_title: Optional[str] = None,
    seo_description: Optional[str] = None,
    show_on_web: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    is_addon: Optional[bool] = None,
    addon_type: Optional[str] = None,
    addon_sort: Optional[int] = None,
    addon_code: Optional[str] = None,
    import_page_url: Optional[str] = None,
    compare_urls: Optional[Any] = None,
    fallback_image: str = '',
    touch_specs: bool = False,
    touch_specs_ar: bool = False,
    touch_description_ar: bool = False,
    touch_offer: bool = False,
    touch_seo: bool = False,
    touch_web_flags: bool = False,
    touch_import_page_url: bool = False,
    touch_compare_urls: bool = False,
) -> Tuple[bool, str]:
    """Merge specifications, Arabic content, offer, SEO, and/or web flags into product_detail meta."""
    if (
        not touch_specs
        and not touch_specs_ar
        and not touch_description_ar
        and not touch_offer
        and not touch_seo
        and not touch_web_flags
        and not touch_import_page_url
        and not touch_compare_urls
    ):
        return (True, '')
    if not media_db.media_table_ready():
        if touch_offer and offer_price is not None:
            return (False, 'Offer price requires the MH_MEDIA table.')
        if touch_web_flags:
            return (False, 'Website visibility requires the MH_MEDIA table.')
        if touch_compare_urls:
            return (False, 'Comparison URLs require the MH_MEDIA table.')
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

    if touch_seo:
        title_text = _clean_text(seo_title)[:_SEO_TITLE_MAX]
        desc_text = _clean_text(seo_description)[:_SEO_DESC_MAX]
        if title_text:
            meta['seo_title'] = title_text
        else:
            meta.pop('seo_title', None)
        if desc_text:
            meta['seo_description'] = desc_text
        else:
            meta.pop('seo_description', None)

    if touch_web_flags:
        if show_on_web is False:
            meta['show_on_web'] = False
        else:
            meta.pop('show_on_web', None)
        if is_featured:
            meta['is_featured'] = True
        else:
            meta.pop('is_featured', None)
        if is_addon:
            meta['is_addon'] = True
            addon_kind = str(addon_type or meta.get('addon_type') or 'gift_wrap').strip().lower()
            meta['addon_type'] = addon_kind or 'gift_wrap'
            if addon_sort is not None:
                meta['addon_sort'] = int(addon_sort)
            code = str(addon_code or meta.get('addon_code') or '').strip().lower()
            if code:
                meta['addon_code'] = code
            meta['show_on_web'] = False
        else:
            meta.pop('is_addon', None)
            meta.pop('addon_type', None)
            meta.pop('addon_sort', None)
            meta.pop('addon_code', None)

    if touch_import_page_url:
        page_url = _clean_import_page_url(import_page_url)
        if page_url:
            meta['import_page_url'] = page_url
        else:
            meta.pop('import_page_url', None)

    if touch_compare_urls:
        urls = clean_compare_urls(compare_urls)
        if urls:
            meta['compare_urls'] = urls
            packed: Dict[str, Any] = {'compare_urls': urls}
            for key, value in meta.items():
                if key != 'compare_urls':
                    packed[key] = value
            meta = packed
            shrink_keys = (
                'specifications',
                'specifications_ar',
                'description_ar',
                'seo_description',
            )
            while len(json.dumps(meta, ensure_ascii=False)) > 3900:
                trimmed = False
                for key in shrink_keys:
                    value = meta.get(key)
                    if isinstance(value, str) and len(value) > 80:
                        meta[key] = value[:-80].rstrip()
                        trimmed = True
                        break
                if not trimmed:
                    break
        else:
            meta.pop('compare_urls', None)

    has_specs = bool(str(meta.get('specifications') or '').strip())
    has_specs_ar = bool(str(meta.get('specifications_ar') or '').strip())
    has_desc_ar = bool(str(meta.get('description_ar') or '').strip())
    has_offer = _parse_offer(meta.get('offer_price')) is not None
    has_seo = bool(_clean_text(meta.get('seo_title')) or _clean_text(meta.get('seo_description')))
    has_web_flags = (
        (not show_on_web_from_meta(meta))
        or is_featured_from_meta(meta)
        or is_addon_from_meta(meta)
    )
    has_import_url = bool(_clean_import_page_url(meta.get('import_page_url')))
    has_compare_urls = bool(clean_compare_urls(meta.get('compare_urls')))
    if (
        not has_specs
        and not has_specs_ar
        and not has_desc_ar
        and not has_offer
        and not has_seo
        and not has_web_flags
        and not has_import_url
        and not has_compare_urls
    ):
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
