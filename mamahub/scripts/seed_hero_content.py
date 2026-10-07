#!/usr/bin/env python3
"""Seed recommended MamaHub homepage hero content."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

HERO_META = {
    'eyebrow': "Qatar's family toy store",
    'panel_class': 'bg-gradient-to-br from-brand-purple via-[#a855f7] to-brand-accent',
    'primary_cta': {'label': 'Shop toys', 'href': '/products'},
    'secondary_cta': {'label': 'Gift finder', 'href': '/gift-finder', 'icon': 'gift'},
}


def main() -> None:
    ok, msg, slide = media_db.upsert_media({
        'placement': 'hero',
        'ref_key': 'main',
        'title': 'Make every day a play day',
        'subtitle': 'Trusted toys and gifts for babies, kids, and families in Qatar.',
        'image_url': '/media/files/03c8e09282ad-photo.avif',
        'link_url': '/products',
        'alt_text': 'Happy family play time',
        'sort_order': 0,
        'is_active': True,
        'meta': HERO_META,
    })
    print('hero slide:', ok, msg)

    ok, msg, bg = media_db.upsert_media({
        'media_id': 1,
        'placement': 'hero_bg',
        'ref_key': None,
        'title': None,
        'subtitle': None,
        'image_url': '/media/files/a57fb5f43cc4-hero.mp4',
        'link_url': None,
        'alt_text': 'Family playing at home',
        'sort_order': 0,
        'is_active': True,
        'meta': {'poster_url': '/media/files/03c8e09282ad-photo.avif'},
    })
    print('hero_bg:', ok, msg)

    rows, _ = media_db.list_media(placement='hero', active_only=True)
    print(json.dumps(rows, indent=2, default=str))


if __name__ == '__main__':
    main()
