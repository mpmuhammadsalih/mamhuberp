#!/usr/bin/env python3
"""Seed MamaHub homepage promo tiles with real images."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

PROMOS = [
    {
        'ref_key': 'new-arrivals',
        'title': 'New Arrivals',
        'subtitle': 'Check out the latest toys kids will love!',
        'link_url': '/new-arrivals',
        'image_url': '/media/files/03c8e09282ad-photo.avif',
        'sort_order': 1,
        'meta': {
            'cta': 'Explore Now',
            'badge': 'new',
            'bg': 'bg-gradient-to-br from-brand-tint via-brand-cream-alt to-white',
            'deco': 'from-brand-accent/30 to-transparent',
            'title_color': 'text-brand-accent',
            'btn_class': 'bg-brand-accent hover:bg-brand-accent-hover',
            'badge_bg': 'bg-brand-accent',
        },
    },
    {
        'ref_key': 'lego',
        'title': 'LEGO Collection',
        'subtitle': 'Build, play and imagine endless adventures',
        'link_url': '/products?q=LEGO',
        'image_url': 'https://images.unsplash.com/photo-1558060370-d644479cb6df?w=600&q=80',
        'sort_order': 2,
        'meta': {
            'cta': 'Shop LEGO',
            'badge_icon': 'lego',
            'bg': 'bg-gradient-to-br from-[#EFF6FF] via-[#F0F7FF] to-[#E0F0FE]',
            'deco': 'from-sky-200/40 to-transparent',
            'title_color': 'text-[#0071DC]',
            'btn_class': 'bg-[#0071DC] hover:bg-[#005BB5]',
            'badge_bg': 'bg-[#0071DC]',
        },
    },
    {
        'ref_key': 'outdoor',
        'title': 'Outdoor Fun',
        'subtitle': 'Toys for active kids & happy playtimes',
        'link_url': '/products?q=outdoor',
        'image_url': 'https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=600&q=80',
        'sort_order': 3,
        'meta': {
            'cta': 'Shop Now',
            'badge_icon': 'scooter',
            'bg': 'bg-gradient-to-br from-[#EDFFF3] via-[#F0FFF5] to-[#E2FAEB]',
            'deco': 'from-emerald-200/40 to-transparent',
            'title_color': 'text-[#00B04F]',
            'btn_class': 'bg-[#00B04F] hover:bg-[#009443]',
            'badge_bg': 'bg-[#00B04F]',
        },
    },
    {
        'ref_key': 'gifts',
        'title': 'Perfect Gifts',
        'subtitle': 'Find the ideal gift for every occasion',
        'link_url': '/gift-finder',
        'image_url': 'https://images.unsplash.com/photo-1513548019107-a513e4e4ea08?w=600&q=80',
        'sort_order': 4,
        'meta': {
            'cta': 'Gift Finder',
            'badge_icon': 'gift',
            'bg': 'bg-gradient-to-br from-[#F5F0FF] via-[#F8F4FF] to-[#EDE4FF]',
            'deco': 'from-violet-200/40 to-transparent',
            'title_color': 'text-[#7E48D3]',
            'btn_class': 'bg-[#7E48D3] hover:bg-[#6B3BB8]',
            'badge_bg': 'bg-[#7E48D3]',
        },
    },
]


def main() -> None:
    for promo in PROMOS:
        ok, msg, row = media_db.upsert_media({
            'placement': 'promo',
            'ref_key': promo['ref_key'],
            'title': promo['title'],
            'subtitle': promo['subtitle'],
            'link_url': promo['link_url'],
            'image_url': promo['image_url'],
            'sort_order': promo['sort_order'],
            'is_active': True,
            'meta': promo['meta'],
        })
        print(promo['ref_key'], ok, msg, row.get('media_id') if row else None)

    rows, _ = media_db.list_media(placement='promo', active_only=True)
    print(json.dumps([{'ref': r.get('ref_key'), 'title': r.get('title'), 'image': r.get('image_url')} for r in rows], indent=2))


if __name__ == '__main__':
    main()
