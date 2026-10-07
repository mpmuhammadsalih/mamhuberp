"""Fetch a Snoonu product page and match it against MamaHub item names."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from addons.ecommerce.services import catalog as catalog_svc
from addons.ecommerce.services import product_page_import as page_import_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from addons.ecommerce.services.common import resolve_location_code
from db import get_item_by_code, get_item_by_code_anywhere, get_items_list

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_TOKEN_RE = re.compile(r'[a-z0-9]{3,}')
_SNOONU_HOSTS = {'snoonu.com', 'www.snoonu.com'}
_SNOONU_ID_RE = re.compile(r'^[a-f0-9]{20,24}$', re.I)
_SNOONU_API_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
    'Origin': 'https://snoonu.com',
    'Referer': 'https://snoonu.com/',
    'Latitude': '25.2854',
    'Longitude': '51.5310',
    'Language': 'en',
    'Snoonu-App-Platform': 'web',
    'Snoonu-App-Version': '1.0.0',
    'Snoonu-App-Device-ID': 'mamahub-snoonu-lookup',
}


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(value or '').lower()))


def _clean_snoonu_url(raw: str) -> str:
    value = str(raw or '').strip()
    if not value:
        return ''
    if not re.match(r'^https?://', value, re.I):
        value = f'https://{value}'
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if host not in _SNOONU_HOSTS:
        raise ValueError('Paste a snoonu.com product link.')
    path = parsed.path or ''
    if '/product/' not in path.lower():
        raise ValueError('That does not look like a Snoonu product page.')
    return f'https://snoonu.com{path}'


def snoonu_product_id(url: str) -> str:
    parts = [p for p in urlparse(str(url or '')).path.split('/') if p]
    if len(parts) >= 3 and parts[0].lower() == 'product' and _SNOONU_ID_RE.match(parts[2]):
        return parts[2]
    return ''


def is_full_snoonu_url(url: str) -> bool:
    return bool(snoonu_product_id(url))


def _fetch_snoonu_api(product_id: str) -> Optional[Dict[str, Any]]:
    if not requests or not product_id:
        return None
    urls = (
        f'https://snooweb-gateway.snoonu.com/api/v1/marketplace/products/{product_id}',
        f'https://snoomarket-web.snoonu.com/api/v1/marketplace/product_page/{product_id}',
    )
    for url in urls:
        try:
            resp = requests.get(url, headers=_SNOONU_API_HEADERS, timeout=20)
        except Exception:
            continue
        if resp.status_code >= 400:
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        info = payload.get('market_place_product_info') if isinstance(payload, dict) else None
        if not isinstance(info, dict) or not (info.get('name') or info.get('english_name')):
            continue
        images = []
        for raw in info.get('images') or info.get('gallery') or info.get('photos') or []:
            if isinstance(raw, dict):
                raw = raw.get('url') or raw.get('src') or raw.get('image') or raw.get('path') or ''
            href = str(raw or '').strip()
            if href.startswith('//'):
                href = f'https:{href}'
            if href.startswith('http'):
                images.append(href)
        slug = str(info.get('url_friendly_name') or '').strip()
        page_url = f'https://snoonu.com/product/{slug}/{product_id}' if slug else f'https://snoonu.com/product/{product_id}'
        specs = []
        for label, key in (
            ('Category', 'market_place_category_name'),
            ('Subcategory', 'market_place_sub_category_name'),
            ('Group', 'market_place_product_group_name'),
            ('SKU', 'id'),
        ):
            value = str(info.get(key) or '').strip()
            if value:
                specs.append(f'{label}: {value}')
        return {
            'title': str(info.get('english_name') or info.get('name') or '').strip(),
            'description': str(info.get('description') or '').strip(),
            'specifications': '\n'.join(specs),
            'image_urls': images[:16],
            'price': info.get('price') or info.get('price_without_discount'),
            'currency': 'QAR',
            'page_url': page_url,
        }
    return None


def _name_score(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _name_verdict(left: str, right: str) -> str:
    score = _name_score(left, right)
    if score >= 0.92:
        return 'exact'
    if score >= 0.45:
        return 'similar'
    return 'different'


def match_local_items(title: str, *, extra_query: str = '', limit: int = 12) -> List[Dict[str, Any]]:
    query = ' '.join((extra_query or title or '').split())[:80]
    if not query:
        return []
    try:
        loc = resolve_location_code()
    except Exception:
        loc = None
    rows, _total = get_items_list(
        location_code=loc,
        search=query,
        page=1,
        items_per_page=40,
        include_lookup_names=True,
    )
    scored: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        code = int(row.get('itemcode') or row.get('ITEMCODE') or 0)
        if code <= 0 or code in seen:
            continue
        name = str(row.get('itemname') or row.get('ITEMNAME') or row.get('name') or '').strip()
        score = _name_score(title, name)
        if extra_query:
            score = max(score, _name_score(extra_query, name))
        if score < 0.18 and extra_query.lower() not in name.lower() and title.lower() not in name.lower():
            continue
        seen.add(code)
        scored.append(
            {
                'item_code': code,
                'item_name': name,
                'barcode': str(row.get('manufacturerid') or row.get('MANUFACTURERID') or '').strip(),
                'price': row.get('retailprice') or row.get('RETAILPRICE'),
                'score': round(score, 3),
                'verdict': _name_verdict(title, name),
            }
        )
    scored.sort(key=lambda item: (-item['score'], item['item_name']))
    return scored[:limit]


def list_missing_image_items(*, page: int = 1, search: str = '', per_page: int = 40) -> Dict[str, Any]:
    items, total, loc = catalog_svc.list_products(
        page=max(1, int(page or 1)),
        per_page=max(1, min(int(per_page or 40), 100)),
        search=(search or '').strip() or None,
        image_filter='missing',
        order_by='itemname',
        order_direction='asc',
    )
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        code = int(item.get('itemcode') or item.get('ITEMCODE') or 0)
        if code <= 0:
            continue
        rows.append(
            {
                'item_code': code,
                'item_name': str(
                    item.get('itemname') or item.get('ITEMNAME') or item.get('name') or ''
                ).strip(),
            }
        )
    return {
        'items': rows,
        'total': int(total or 0),
        'page': max(1, int(page or 1)),
        'per_page': max(1, min(int(per_page or 40), 100)),
        'location_code': loc,
        'search': (search or '').strip(),
    }


def saved_snoonu_url(item_code: int) -> str:
    meta = web_meta_svc.product_web_meta_map().get(str(int(item_code))) or {}
    candidates = [meta.get('import_page_url')]
    for entry in meta.get('compare_urls') or []:
        if isinstance(entry, dict):
            candidates.append(entry.get('url'))
        else:
            candidates.append(entry)
    for raw in candidates:
        value = str(raw or '').strip()
        if not value:
            continue
        host = (urlparse(value if '://' in value else f'https://{value}').hostname or '').lower()
        if host in _SNOONU_HOSTS and '/product/' in value.lower():
            try:
                return _clean_snoonu_url(value)
            except ValueError:
                continue
    return ''


def get_catalog_item(item_code: int) -> Optional[Dict[str, Any]]:
    try:
        loc = resolve_location_code()
    except Exception:
        loc = None
    if not item_code:
        return None
    row = get_item_by_code(int(item_code), loc) if loc is not None else get_item_by_code_anywhere(int(item_code))
    if not row:
        return None
    code = int(row.get('itemcode') or row.get('ITEMCODE') or item_code)
    return {
        'item_code': code,
        'item_name': str(row.get('itemname') or row.get('ITEMNAME') or row.get('name') or '').strip(),
        'barcode': str(row.get('manufacturerid') or row.get('MANUFACTURERID') or '').strip(),
        'price': row.get('retailprice') or row.get('RETAILPRICE'),
        'snoonu_url': saved_snoonu_url(code),
    }


def fetch_snoonu_listing(*, page_url: str = '', item_name: str = '') -> Dict[str, Any]:
    name = str(item_name or '').strip()
    url = str(page_url or '').strip()
    if url:
        url = _clean_snoonu_url(url)
    if url and not is_full_snoonu_url(url) and name:
        try:
            url = page_import_svc.resolve_snoonu_product_url(name, hint_url=url)
        except Exception:
            url = url
    if not is_full_snoonu_url(url) and name:
        try:
            resolved = page_import_svc.resolve_snoonu_product_url(name, hint_url=url)
        except Exception:
            resolved = ''
        if is_full_snoonu_url(resolved):
            url = resolved
    if not is_full_snoonu_url(url):
        raise ValueError(
            'Snoonu needs the full product link, including the ID at the end '
            '(example: /product/bunny-pencil-case--large-capacity-kids-stationery-pouch/6a9139479f3d2f4a580c2b73). '
            'A name-only link returns HTTP 404. Paste the link from the Snoonu product page.'
        )
    extracted = _fetch_snoonu_api(snoonu_product_id(url))
    if not extracted:
        extracted = page_import_svc.extract_product_page(url)
    title = str(extracted.get('title') or '').strip()
    try:
        matches = match_local_items(title, extra_query=name)
    except Exception:
        matches = []
    best = matches[0] if matches else None
    return {
        'ok': True,
        'page_url': extracted.get('page_url') or url,
        'title': title,
        'description': extracted.get('description') or '',
        'specifications': extracted.get('specifications') or '',
        'image_urls': list(extracted.get('image_urls') or [])[:16],
        'price': extracted.get('price'),
        'currency': extracted.get('currency') or 'QAR',
        'item_name': name,
        'matches': matches,
        'best_match': best,
        'name_verdict': _name_verdict(title, name) if name and title else '',
    }
