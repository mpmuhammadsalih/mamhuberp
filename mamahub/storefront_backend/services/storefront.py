"""Storefront home/media payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from addons.ecommerce import media_db
from addons.ecommerce import settings_store
from addons.ecommerce.services import media as media_svc


def _text(store: Dict[str, Any], key: str, fallback: str) -> str:
    value = str(store.get(key) or '').strip()
    return value or fallback


def get_storefront_settings() -> Dict[str, Any]:
    store = settings_store.load_store_settings()
    return {
        'coupons_enabled': bool(store.get('coupons_enabled')),
        'free_gift_wrap': bool(store.get('free_gift_wrap')),
        'checkout_enabled': bool(store.get('checkout_enabled', True)),
        'pickup_enabled': bool(store.get('pickup_enabled', True)),
        'delivery_enabled': bool(store.get('delivery_enabled', True)),
        'header_trust_delivery': _text(
            store, 'header_trust_delivery', settings_store.DEFAULT_SETTINGS['header_trust_delivery']
        ),
        'header_trust_original': _text(
            store, 'header_trust_original', settings_store.DEFAULT_SETTINGS['header_trust_original']
        ),
        'header_trust_returns': _text(
            store, 'header_trust_returns', settings_store.DEFAULT_SETTINGS['header_trust_returns']
        ),
        'header_trust_delivery_ar': _text(
            store, 'header_trust_delivery_ar', settings_store.DEFAULT_SETTINGS['header_trust_delivery_ar']
        ),
        'header_trust_original_ar': _text(
            store, 'header_trust_original_ar', settings_store.DEFAULT_SETTINGS['header_trust_original_ar']
        ),
        'header_trust_returns_ar': _text(
            store, 'header_trust_returns_ar', settings_store.DEFAULT_SETTINGS['header_trust_returns_ar']
        ),
    }


def get_storefront_home() -> Dict[str, Any]:
    rows, _ = media_db.list_media(active_only=True)
    by_placement: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        placement = str(row.get('placement') or '').strip()
        if placement:
            by_placement.setdefault(placement, []).append(row)

    hero_bg = by_placement.get('hero_bg') or []
    hero = by_placement.get('hero') or []
    promo = by_placement.get('promo') or []
    promo.sort(key=lambda row: (row.get('sort_order') or 0, row.get('media_id') or 0))
    banner = by_placement.get('showcase_banner') or []
    logo = by_placement.get('storefront_logo') or []
    showcase: Dict[str, Any] = {}
    for row in banner:
        key = str(row.get('ref_key') or 'default')
        showcase[key] = _public_media_row(row)
    return {
        'storefront_logo': _public_media_row(logo[0]) if logo else None,
        'hero_background': _public_media_row(hero_bg[0]) if hero_bg else None,
        'hero_slides': [_public_media_row(r) for r in hero],
        'promos': [_public_media_row(r) for r in promo],
        'showcase_banners': showcase,
    }


def list_media(*, placement: Optional[str] = None) -> List[Dict[str, Any]]:
    rows, _ = media_db.list_media(placement=placement, active_only=True)
    return [_public_media_row(r) for r in rows]


def _public_media_row(row: Dict[str, Any]) -> Dict[str, Any]:
    image_url = row.get('image_url') or ''
    preview = media_svc.preview_filename(image_url)
    if preview:
        image_url = f'/api/v1/media/files/{preview}'
    meta = dict(row.get('meta') or {})
    poster_url = meta.get('poster_url')
    if poster_url:
        poster_preview = media_svc.preview_filename(str(poster_url))
        if poster_preview:
            meta['poster_url'] = f'/api/v1/media/files/{poster_preview}'
    video_url = meta.get('video_url')
    if video_url:
        video_preview = media_svc.preview_filename(str(video_url))
        if video_preview:
            meta['video_url'] = f'/api/v1/media/files/{video_preview}'
    return {
        **row,
        'image_url': image_url,
        'meta': meta,
    }
