#!/usr/bin/env python3
"""Seed Explore More Categories bento tiles (MH_MEDIA placement explore_category)."""
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAMA_PUBLIC = ROOT.parent / 'mamahub' / 'frontend' / 'public'
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402
from addons.ecommerce.services import media as media_svc  # noqa: E402

MIN_BYTES = 1024

TILES = [
    {
        'ref_key': 'outdoor',
        'title': 'Outdoor & Play',
        'link_url': '/products?q=outdoor',
        'sort_order': 1,
        'source': MAMA_PUBLIC / 'demo-products' / '01-toys.jpg',
    },
    {
        'ref_key': 'lego',
        'title': 'LEGO & Building',
        'link_url': '/products?q=lego',
        'sort_order': 2,
        'source': MAMA_PUBLIC / 'demo-products' / '10.jpg',
    },
    {
        'ref_key': 'baby',
        'title': 'Baby & Toddler',
        'link_url': '/products?age=0-2',
        'sort_order': 3,
        'source': MAMA_PUBLIC / 'demo-products' / '20.jpg',
    },
    {
        'ref_key': 'games',
        'title': 'Games & Puzzles',
        'link_url': '/products?q=game',
        'sort_order': 4,
        'source': MAMA_PUBLIC / 'demo-products' / '12.jpg',
    },
    {
        'ref_key': 'gifts',
        'title': 'Gifts & Party',
        'link_url': '/gift-finder',
        'sort_order': 5,
        'source': MAMA_PUBLIC / 'demo-products' / '11-spices.jpg',
    },
]


def copy_image(source: Path, label: str) -> str:
    if not source.is_file() or source.stat().st_size < MIN_BYTES:
        raise FileNotFoundError(f'Missing image: {source}')
    ext = source.suffix.lower() or '.jpg'
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in label)[:40]
    filename = f'{uuid.uuid4().hex[:12]}-explore-{safe}{ext}'
    target = media_svc.uploads_dir() / filename
    shutil.copy2(source, target)
    return f'/media/files/{filename}'


def upsert_tile(tile: dict, image_url: str) -> None:
    ref_key = tile['ref_key']
    rows, _ = media_db.list_media(placement='explore_category', active_only=False)
    existing = next((r for r in rows if str(r.get('ref_key')) == ref_key), None)
    payload = {
        'media_id': existing.get('media_id') if existing else None,
        'placement': 'explore_category',
        'ref_key': ref_key,
        'title': tile['title'],
        'subtitle': None,
        'image_url': image_url,
        'link_url': tile['link_url'],
        'sort_order': tile['sort_order'],
        'is_active': True,
        'meta': {},
    }
    ok, msg, _ = media_db.upsert_media(payload)
    print(ref_key, ok, msg)


def main() -> None:
    for tile in TILES:
        image_url = copy_image(tile['source'], tile['ref_key'])
        upsert_tile(tile, image_url)


if __name__ == '__main__':
    main()
