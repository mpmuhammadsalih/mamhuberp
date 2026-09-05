#!/usr/bin/env python3
"""Seed LuLu-style movable promo banner slides in MH_MEDIA."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402
from addons.ecommerce.services import media as media_svc  # noqa: E402

ASSET_DIR = ROOT / 'scripts' / 'assets' / 'promos'

PROMOS = [
    {
        'ref_key': 'strip-1',
        'title': 'MamaHub Rewards — 10% off first order',
        'subtitle': 'Use code MAMA10 on your first order',
        'link_url': '/offers',
        'sort_order': 1,
        'asset': 'strip-1.svg',
        'meta': {'layout': 'strip', 'image_only': True},
    },
    {
        'ref_key': 'slide-1-main',
        'title': 'Weekly Deals',
        'subtitle': 'Toys, games and gifts kids will love',
        'link_url': '/offers',
        'sort_order': 2,
        'asset': 'slide-1-main.svg',
        'meta': {'slot': 'main', 'slide': 1, 'image_only': True, 'cta': 'Shop now'},
    },
    {
        'ref_key': 'slide-1-side',
        'title': 'Free home delivery',
        'subtitle': 'For all orders above',
        'link_url': '/products',
        'sort_order': 3,
        'asset': 'slide-1-side.svg',
        'meta': {'slot': 'side', 'slide': 1, 'image_only': True, 'badge_text': 'QAR 150/-'},
    },
    {
        'ref_key': 'slide-2-main',
        'title': 'New Arrivals',
        'subtitle': 'Fresh toys and games just landed',
        'link_url': '/new-arrivals',
        'sort_order': 4,
        'asset': 'slide-2-main.svg',
        'meta': {'slot': 'main', 'slide': 2, 'image_only': True, 'cta': 'Explore now'},
    },
    {
        'ref_key': 'slide-2-side',
        'title': 'Perfect gift ideas',
        'subtitle': 'For every occasion',
        'link_url': '/gift-finder',
        'sort_order': 5,
        'asset': 'slide-2-side.svg',
        'meta': {'slot': 'side', 'slide': 2, 'image_only': True},
    },
]


def ensure_asset_in_uploads(asset_name: str) -> str:
    source = ASSET_DIR / asset_name
    if not source.is_file():
        raise FileNotFoundError(f'Missing promo asset: {source}')

    uploads = media_svc.uploads_dir()
    target_name = f'mamahub-{asset_name}'
    target = uploads / target_name
    shutil.copyfile(source, target)
    return f'/media/files/{target_name}'


def upsert(item: dict) -> None:
    rows, _ = media_db.list_media(placement='promo', active_only=False)
    existing = next((r for r in rows if r.get('ref_key') == item['ref_key']), None)
    image_url = ensure_asset_in_uploads(item['asset'])
    payload = {
        'media_id': existing.get('media_id') if existing else None,
        'placement': 'promo',
        'ref_key': item['ref_key'],
        'title': item['title'],
        'subtitle': item['subtitle'],
        'image_url': image_url,
        'link_url': item['link_url'],
        'alt_text': item['title'],
        'sort_order': item['sort_order'],
        'is_active': True,
        'meta': item.get('meta') or {},
    }
    ok, msg, _ = media_db.upsert_media(payload)
    print(item['ref_key'], image_url, ok, msg)


if __name__ == '__main__':
    for row in PROMOS:
        upsert(row)
