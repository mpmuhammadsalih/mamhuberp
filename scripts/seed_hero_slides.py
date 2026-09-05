#!/usr/bin/env python3
"""Seed multiple homepage hero slides with different panel backgrounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

POSTER = '/media/files/7fd3bd29e383-premium_photo-1661558951515-47f7706fd9c6.avif'

SLIDES = [
    {
        'ref_key': 'main',
        'sort_order': 0,
        'title': 'Make every day a play day',
        'subtitle': 'Trusted toys and gifts for babies, kids, and families in Qatar.',
        'image_url': POSTER,
        'link_url': '/products',
        'alt_text': 'Happy family play time',
        'meta': {
            'eyebrow': "Qatar's family toy store",
            'panel_class': 'bg-gradient-to-br from-brand-purple via-violet-500 to-brand-accent',
            'primary_cta': {'label': 'Shop toys', 'href': '/products'},
            'secondary_cta': {'label': 'Gift finder', 'href': '/gift-finder', 'icon': 'gift'},
        },
    },
    {
        'ref_key': 'gifts',
        'sort_order': 1,
        'title': 'Find the perfect gift',
        'subtitle': 'Use our gift finder to match toys to age, interests, and budget.',
        'image_url': POSTER,
        'link_url': '/gift-finder',
        'alt_text': 'Gift ideas for kids',
        'meta': {
            'eyebrow': 'Gifts for every age',
            'panel_class': 'bg-gradient-to-br from-brand-teal via-cyan-500 to-brand-yellow',
            'primary_cta': {'label': 'Gift finder', 'href': '/gift-finder'},
            'secondary_cta': {'label': 'Shop toys', 'href': '/products'},
        },
    },
    {
        'ref_key': 'outdoor',
        'sort_order': 2,
        'title': 'Outdoor adventures await',
        'subtitle': 'Ride-ons, sports, and garden play for sunny days in Qatar.',
        'image_url': POSTER,
        'link_url': '/products?q=outdoor',
        'alt_text': 'Outdoor toys',
        'meta': {
            'eyebrow': 'Summer fun',
            'panel_class': 'bg-gradient-to-br from-brand-orange via-amber-400 to-rose-500',
            'primary_cta': {'label': 'Shop outdoor', 'href': '/products?q=outdoor'},
            'secondary_cta': {'label': 'Shop by age', 'href': '/products'},
        },
    },
]


def _media_id_for_ref(ref_key: str) -> int | None:
    rows, _ = media_db.list_media(placement='hero', active_only=False)
    for row in rows:
        if str(row.get('ref_key') or '') == ref_key:
            media_id = row.get('media_id')
            if media_id is not None:
                return int(media_id)
    return None


def main() -> None:
    for slide in SLIDES:
        payload = {
            **slide,
            'placement': 'hero',
            'is_active': True,
        }
        media_id = _media_id_for_ref(slide['ref_key'])
        if media_id:
            payload['media_id'] = media_id
        ok, msg, _ = media_db.upsert_media(payload)
        print(slide['ref_key'], ok, msg)

    rows, _ = media_db.list_media(placement='hero', active_only=True)
    print(json.dumps([{'ref_key': r.get('ref_key'), 'title': r.get('title')} for r in rows], indent=2))


if __name__ == '__main__':
    main()
