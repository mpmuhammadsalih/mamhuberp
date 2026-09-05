#!/usr/bin/env python3
"""Copy local product photos into MH_MEDIA for Shop by category."""
from __future__ import annotations

import shutil
import sys
import uuid
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAMA_PUBLIC = ROOT.parent / 'mamahub' / 'frontend' / 'public'
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from addons.ecommerce import media_db  # noqa: E402
from addons.ecommerce.services import media as media_svc  # noqa: E402
from storefront_backend.services.catalog import get_category_tree  # noqa: E402

MIN_BYTES = 1024

# Real JPEGs from storefront public assets (skip 29-byte git placeholders).
SOURCE_IMAGES = [
    MAMA_PUBLIC / 'demo-products' / '01-toys.jpg',
    MAMA_PUBLIC / 'demo-products' / '03-snacks.jpg',
    MAMA_PUBLIC / 'demo-products' / '03-bottles.jpg',
    MAMA_PUBLIC / 'demo-products' / '05-shampoo.jpg',
    MAMA_PUBLIC / 'demo-products' / '07-beverage.jpg',
    MAMA_PUBLIC / 'demo-products' / '06-skincare.jpg',
    MAMA_PUBLIC / 'demo-products' / '11-spices.jpg',
    MAMA_PUBLIC / 'demo-products' / '01-toothpaste.jpg',
]

# Existing uploaded promo/age photos already on the media server.
REMOTE_IMAGES = [
    '/media/files/728ac605a6d8-istockphoto-2217901800-612x612.jpg',
    '/media/files/c83802fe0715-istockphoto-2199317632-612x612.jpg',
    '/media/files/6991a3533bef-istockphoto-2239512002-612x612.jpg',
]


def homepage_categories(limit: int = 8) -> list[dict]:
    items: list[dict] = []
    for main in get_category_tree():
        children = main.get('children') or []
        if children:
            for dept in children:
                items.append({
                    'code': dept.get('code'),
                    'name': dept.get('name'),
                    'href': f"/products?main={main.get('code')}&dept={dept.get('code')}",
                })
                if len(items) >= limit:
                    return items
        else:
            items.append({
                'code': main.get('code'),
                'name': main.get('name'),
                'href': f"/products?main={main.get('code')}",
            })
            if len(items) >= limit:
                return items
    return items


def copy_local_image(source: Path, label: str) -> str:
    if not source.is_file() or source.stat().st_size < MIN_BYTES:
        raise FileNotFoundError(f'Missing or too small: {source}')
    ext = source.suffix.lower() or '.jpg'
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in label)[:40]
    filename = f'{uuid.uuid4().hex[:12]}-cat-{safe}{ext}'
    target = media_svc.uploads_dir() / filename
    shutil.copy2(source, target)
    return f'/media/files/{filename}'


def download_server_image(path: str, label: str) -> str:
    url = f'http://localhost:5055/api/v1{path}'
    req = urllib.request.Request(url, headers={'User-Agent': 'MamaHubSeed/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    if len(content) < MIN_BYTES:
        raise ValueError(f'Download too small: {url}')
    ext = Path(path).suffix.lower() or '.jpg'
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in label)[:40]
    filename = f'{uuid.uuid4().hex[:12]}-cat-{safe}{ext}'
    target = media_svc.uploads_dir() / filename
    target.write_bytes(content)
    return f'/media/files/{filename}'


def resolve_source(idx: int, label: str) -> str:
    if idx < len(REMOTE_IMAGES):
        try:
            return download_server_image(REMOTE_IMAGES[idx], label)
        except Exception as exc:
            print('remote fallback', REMOTE_IMAGES[idx], exc)
    source = SOURCE_IMAGES[idx % len(SOURCE_IMAGES)]
    return copy_local_image(source, label)


def upsert_category(code: int, name: str, href: str, image_url: str, sort_order: int) -> None:
    ref_key = str(code)
    rows, _ = media_db.list_media(placement='category', active_only=False)
    existing = next((r for r in rows if str(r.get('ref_key')) == ref_key), None)
    payload = {
        'media_id': existing.get('media_id') if existing else None,
        'placement': 'category',
        'ref_key': ref_key,
        'title': name,
        'subtitle': None,
        'image_url': image_url,
        'link_url': href,
        'sort_order': sort_order,
        'is_active': True,
        'meta': {},
    }
    ok, msg, _ = media_db.upsert_media(payload)
    print(ref_key, name, image_url, ok, msg)


if __name__ == '__main__':
    cats = homepage_categories(8)
    for idx, cat in enumerate(cats):
        code = cat.get('code')
        name = str(cat.get('name') or f'Category {code}')
        if code is None:
            continue
        label = f'{int(code)}-{name}'
        local_url = resolve_source(idx, label)
        upsert_category(int(code), name, str(cat.get('href') or '/products'), local_url, idx + 1)
