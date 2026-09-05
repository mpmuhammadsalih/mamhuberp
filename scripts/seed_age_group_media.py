#!/usr/bin/env python3
"""Seed Shop by age images in MH_MEDIA (placement age_group)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

AGE_IMAGES = [
    {
        'ref_key': '0-12-months',
        'title': '0-12 months',
        'image_url': 'https://images.unsplash.com/photo-1515488042361-ee00e8170dc8?w=600&q=80',
        'sort_order': 1,
    },
    {
        'ref_key': '1-2-years',
        'title': '1-2 years',
        'image_url': 'https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?w=600&q=80',
        'sort_order': 2,
    },
    {
        'ref_key': '3-5-years',
        'title': '3-5 years',
        'image_url': 'https://images.unsplash.com/photo-1558060370-d644479cb6df?w=600&q=80',
        'sort_order': 3,
    },
    {
        'ref_key': '6-8-years',
        'title': '6-8 years',
        'image_url': 'https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=600&q=80',
        'sort_order': 4,
    },
]


def upsert(item: dict) -> None:
    rows, _ = media_db.list_media(placement='age_group', active_only=False)
    existing = next((r for r in rows if r.get('ref_key') == item['ref_key']), None)
    payload = {
        'media_id': existing.get('media_id') if existing else None,
        'placement': 'age_group',
        'ref_key': item['ref_key'],
        'title': item['title'],
        'subtitle': None,
        'image_url': item['image_url'],
        'link_url': f"/products?age={item['ref_key']}",
        'sort_order': item['sort_order'],
        'is_active': True,
        'meta': {},
    }
    ok, msg, _ = media_db.upsert_media(payload)
    print(item['ref_key'], ok, msg)


if __name__ == '__main__':
    for row in AGE_IMAGES:
        upsert(row)
