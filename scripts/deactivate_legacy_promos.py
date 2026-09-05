#!/usr/bin/env python3
"""Deactivate legacy 4-tile promo rows (pre LuLu carousel)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402

LEGACY_KEYS = {'new-arrivals', 'lego', 'outdoor', 'gifts'}


def main() -> None:
    rows, _ = media_db.list_media(placement='promo', active_only=False)
    for row in rows:
        ref_key = str(row.get('ref_key') or '').strip().lower()
        media_id = row.get('media_id')
        if not media_id or ref_key not in LEGACY_KEYS:
            continue
        ok, msg = media_db.deactivate_media(int(media_id))
        print(ref_key, ok, msg)


if __name__ == '__main__':
    main()
