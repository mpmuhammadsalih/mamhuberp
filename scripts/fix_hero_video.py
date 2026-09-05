#!/usr/bin/env python3
"""Point hero_bg at a valid uploaded MP4 (skips corrupt tiny files)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402
from addons.ecommerce.services import media as media_svc  # noqa: E402

UPLOAD_DIR = media_svc.uploads_dir()
MIN_VIDEO_BYTES = 10_000
REAL_VIDEO = '/media/files/d233cb0024c6-Baby_tells_joke_in_living_202608191937.mp4'
POSTER = '/media/files/7fd3bd29e383-premium_photo-1661558951515-47f7706fd9c6.avif'


def pick_best_video() -> str:
    best: tuple[int, str] | None = None
    for path in UPLOAD_DIR.glob('*.mp4'):
        size = path.stat().st_size
        if size < MIN_VIDEO_BYTES:
            continue
        url = f'/media/files/{path.name}'
        if best is None or size > best[0]:
            best = (size, url)
    return best[1] if best else REAL_VIDEO


def main() -> None:
    video_url = pick_best_video()
    print('using video:', video_url)

    ok, msg, _ = media_db.upsert_media({
        'media_id': 1,
        'placement': 'hero_bg',
        'ref_key': None,
        'title': None,
        'subtitle': None,
        'image_url': video_url,
        'link_url': None,
        'alt_text': 'Family playing at home',
        'sort_order': 0,
        'is_active': True,
        'meta': {'poster_url': POSTER},
    })
    print('hero_bg:', ok, msg)

    ok2, msg2, _ = media_db.upsert_media({
        'media_id': 3,
        'placement': 'hero',
        'ref_key': 'main',
        'title': 'Make every day a play day',
        'subtitle': 'Trusted toys and gifts for babies, kids, and families in Qatar.',
        'image_url': POSTER,
        'link_url': '/products',
        'alt_text': 'Happy family play time',
        'sort_order': 0,
        'is_active': True,
        'meta': {
            'eyebrow': "Qatar's family toy store",
            'panel_class': 'bg-gradient-to-br from-brand-purple via-[#a855f7] to-brand-accent',
            'primary_cta': {'label': 'Shop toys', 'href': '/products'},
            'secondary_cta': {'label': 'Gift finder', 'href': '/gift-finder', 'icon': 'gift'},
        },
    })
    print('hero slide:', ok2, msg2)


if __name__ == '__main__':
    main()
