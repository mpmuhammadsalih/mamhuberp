#!/usr/bin/env python3
"""Deactivate seeded MamaHub promo banner rows."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

TARGET_KEYS = {'top-strip', 'main', 'side'}
TARGET_FILES = {
    'mamahub-promo-top-strip.svg',
    'mamahub-promo-weekly-deals.svg',
    'mamahub-promo-free-delivery.svg',
}


def main() -> None:
    rows, _ = media_db.list_media(placement='promo', active_only=False)
    for row in rows:
        ref_key = str(row.get('ref_key') or '').strip().lower()
        image_url = str(row.get('image_url') or '')
        media_id = row.get('media_id')
        if not media_id:
            continue
        if ref_key in TARGET_KEYS or any(name in image_url for name in TARGET_FILES):
            ok, msg = media_db.deactivate_media(int(media_id))
            print(ref_key or image_url, ok, msg)


if __name__ == '__main__':
    main()
