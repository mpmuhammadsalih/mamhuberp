"""Find competitor product URLs from the MamaHub photo, name, and store master."""
from __future__ import annotations

import base64
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from addons.ecommerce import compare_stores_db
from addons.ecommerce.services import catalog as catalog_svc
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import product_page_import as page_import_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from addons.ecommerce.services.common import resolve_location_code
from db import get_item_by_code

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
_SEARCH_TIMEOUT = 12
_VISION_TIMEOUT = 45
_MAX_IMAGE_BYTES = 1500 * 1024
_MAX_CANDIDATES = 8
_SKIP_PATH_PARTS = (
    '/search',
    '/cart',
    '/login',
    '/account',
    '/checkout',
    '/wishlist',
    '/help',
    '/about',
    '/contact',
    '/category/',
    '/categories/',
    '/collections/',
    '/gp/search',
    '/s/',
    '/sch/',
)
_JUNK_HOST_PARTS = (
    'wikipedia.',
    'youtube.',
    'youtu.be',
    'facebook.',
    'instagram.',
    'pinterest.',
    'reddit.',
    'twitter.',
    'tiktok.',
    'linkedin.',
    'quora.',
    'medium.com',
    'blogspot.',
    'wordpress.com',
    'duckduckgo.',
    'bing.com',
    'google.',
    'yahoo.',
    'msn.com',
    'shutterstock.',
    'gettyimages.',
    'istockphoto.',
)
_PRODUCT_PATH_HINTS = (
    '/product',
    '/products/',
    '/p/',
    '/dp/',
    '/itm/',
    '/ip/',
    '/pd/',
)
_STORE_HOST_HINTS = (
    ('snoonu', 'snoonu.com'),
    ('virgin', 'virginmegastore.qa'),
    ('lulu', 'luluhypermarket.com'),
    ('carrefour', 'carrefourqatar.com'),
    ('al meera', 'almeera.qa'),
    ('almeera', 'almeera.com.qa'),
    ('family food', 'familyfoodcentre.com'),
    ('jarir', 'jarir.com.qa'),
)
_QATAR_HOSTS = (
    'snoonu.com',
    'virginmegastore.qa',
    'carrefourqatar.com',
    'almeera.qa',
    'almeera.com.qa',
    'familyfoodcentre.com',
    'jarir.com.qa',
)
_NON_QATAR_TLDS = (
    '.ae',
    '.uk',
    '.us',
    '.de',
    '.fr',
    '.in',
    '.sg',
    '.au',
    '.ca',
    '.sa',
    '.kw',
    '.bh',
    '.om',
    '.eg',
)
_NON_QATAR_HOSTS = (
    'amazon.com',
    'amazon.ae',
    'amazon.co.uk',
    'noon.com',
    'jumbo.ae',
    'toysrus.ae',
    'firstcry.ae',
    'mumzworld.com',
    'aliexpress.com',
    'alibaba.com',
    'ebay.com',
    'temu.com',
    'shein.com',
    'walmart.com',
    'target.com',
)
_OWN_HOSTS = ('mamahub',)
_DDG_UDDG_RE = re.compile(r'uddg=([^&"\s]+)', re.I)
_HREF_RE = re.compile(r'''href=["'](https?://[^"'#\s]+)["']''', re.I)
_BING_RE = re.compile(
    r'<h2[^>]*>\s*<a[^>]+href=["\'](https?://[^"\']+)["\']',
    re.I,
)


def openai_configured() -> bool:
    return bool((os.environ.get('OPENAI_API_KEY') or '').strip())


def _openai_model() -> str:
    return (
        (os.environ.get('OPENAI_VISION_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o').strip()
        or 'gpt-4o'
    )


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()


def default_search_name(product: Optional[Dict[str, Any]] = None, item_name: str = '') -> str:
    """Short editable search text: item name without barcodes or stock codes."""
    name = _clean_text(item_name or (product or {}).get('item_name'))
    name = re.sub(r'\b\d{8,}\b', ' ', name)
    name = re.sub(r'\b(?:sku|itemcode|item\s*code|barcode)\b[:#]?\s*', ' ', name, flags=re.I)
    return ' '.join(name.split()).strip()[:120]


def _host_of(url: str) -> str:
    host = (urlparse(str(url or '')).hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


def _is_own_host(host: str) -> bool:
    name = (host or '').lower()
    return any(part in name for part in _OWN_HOSTS)


def _store_hosts(store: Dict[str, Any]) -> List[str]:
    hosts: List[str] = []
    website = _clean_text(store.get('website_url'))
    if website:
        if '://' not in website:
            website = f'https://{website}'
        host = _host_of(website)
        if host and not _is_own_host(host):
            hosts.append(host)
    name = _clean_text(store.get('store_name')).lower()
    for needle, host in _STORE_HOST_HINTS:
        if needle in name and host not in hosts:
            hosts.append(host)
    return hosts


def _is_junk_host(host: str) -> bool:
    name = (host or '').lower()
    return _is_own_host(name) or any(part in name for part in _JUNK_HOST_PARTS)


def _is_qatar_store_url(url: str) -> bool:
    """Keep only shops based in Qatar (.qa, Qatar hosts, or a Qatar store path)."""
    host = _host_of(url)
    path = (urlparse(url).path or '').lower()
    if not host or _is_junk_host(host):
        return False
    if any(host == blocked or host.endswith('.' + blocked) for blocked in _NON_QATAR_HOSTS):
        return False
    if any(host.endswith(tld) for tld in _NON_QATAR_TLDS):
        return False
    if host.endswith('.qa') or host.endswith('.com.qa'):
        return True
    if 'qatar' in host:
        return True
    if any(host == allowed or host.endswith('.' + allowed) for allowed in _QATAR_HOSTS):
        return True
    if host.endswith('luluhypermarket.com') and ('/en-qa' in path or '/qa/' in path or 'qatar' in path):
        return True
    return False


def _looks_like_product_url(url: str, host: str = '') -> bool:
    found_host = _host_of(url)
    if not found_host or _is_junk_host(found_host):
        return False
    if host and found_host != host:
        return False
    path = (urlparse(url).path or '/').lower()
    if path in ('', '/'):
        return False
    if any(part in path for part in _SKIP_PATH_PARTS) and not any(
        hint in path for hint in _PRODUCT_PATH_HINTS
    ):
        return False
    return True


def _score_url(url: str, query: str) -> int:
    path = (urlparse(url).path or '').lower()
    score = 0
    for hint in _PRODUCT_PATH_HINTS:
        if hint in path:
            score += 4
            break
    tokens = [tok for tok in re.split(r'[^a-z0-9]+', query.lower()) if len(tok) > 2]
    slug = re.sub(r'[^a-z0-9]+', ' ', path)
    score += sum(2 for tok in tokens if tok in slug)
    if any(part in path for part in _SKIP_PATH_PARTS):
        score -= 6
    host = _host_of(url)
    if host.endswith('.qa') or host.endswith('.com.qa') or 'qatar' in host:
        score += 5
    if '/en-qa' in path or '/qa/' in path:
        score += 3
    return score


def _normalize_found_url(raw: str) -> str:
    value = html.unescape(unquote(str(raw or '').strip()))
    if not value:
        return ''
    if value.startswith('//'):
        value = f'https:{value}'
    try:
        return page_import_svc._normalize_page_url(value)
    except Exception:
        return ''


def _extract_result_urls(html_text: str) -> List[str]:
    found: List[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        url = _normalize_found_url(raw)
        key = url.rstrip('/').lower()
        if not url or key in seen or _is_own_host(_host_of(url)):
            return
        seen.add(key)
        found.append(url)

    for encoded in _DDG_UDDG_RE.findall(html_text or ''):
        add(unquote(encoded))
    for href in _HREF_RE.findall(html_text or ''):
        if 'duckduckgo.' in href or 'bing.com' in href or 'microsoft.com' in href:
            continue
        add(href)
    for href in _BING_RE.findall(html_text or ''):
        add(href)
    return found


def _search_html(url: str, *, params: Optional[Dict[str, str]] = None, data: Optional[Dict[str, str]] = None) -> str:
    if not requests:
        return ''
    try:
        method = requests.post if data is not None else requests.get
        resp = method(
            url,
            params=params,
            data=data,
            headers={'User-Agent': _UA, 'Accept': 'text/html', 'Accept-Language': 'en-US,en;q=0.9'},
            timeout=_SEARCH_TIMEOUT,
        )
        if resp.status_code >= 400:
            return ''
        return html.unescape(resp.text or '')
    except Exception:
        return ''


def _web_search_urls(query: str) -> List[str]:
    text = _clean_text(query)
    if not text:
        return []
    results: List[str] = []
    seen: set[str] = set()
    pages = [
        _search_html('https://html.duckduckgo.com/html/', data={'q': text[:180]}),
        _search_html('https://www.bing.com/search', params={'q': text[:180]}),
    ]
    for page in pages:
        for url in _extract_result_urls(page):
            key = url.rstrip('/').lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(url)
    return results


def _store_label_from_host(host: str) -> str:
    name = (host or '').lower()
    for needle, known in _STORE_HOST_HINTS:
        if name == known or name.endswith('.' + known):
            return needle.replace('toys r us', 'Toys R Us').title() if needle != 'toys r us' else 'Toys R Us'
    if name.endswith('snoonu.com'):
        return 'Snoonu'
    if name.endswith('virginmegastore.qa') or name.endswith('virginmegastore.com'):
        return 'Virgin'
    base = name.split('.')[0]
    return base.replace('-', ' ').replace('_', ' ').title()[:80] or 'Web store'


def _match_store_for_host(host: str, stores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    name = (host or '').lower()
    if not name:
        return None
    for store in stores:
        if name in _store_hosts(store):
            return store
        website_host = _host_of(str(store.get('website_url') or ''))
        if website_host and (name == website_host or name.endswith('.' + website_host)):
            return store
        store_name = _clean_text(store.get('store_name')).lower().replace(' ', '')
        token = name.split('.')[0].replace('-', '')
        if store_name and token and len(token) >= 4 and (token in store_name or store_name in token):
            return store
    return None


def _match_or_create_store(url: str, stores: List[Dict[str, Any]]) -> Dict[str, Any]:
    host = _host_of(url)
    matched = _match_store_for_host(host, stores)
    if matched:
        return matched
    label = _store_label_from_host(host)
    existing_id = compare_stores_db.find_store_id_by_name(label)
    if existing_id:
        row = compare_stores_db.get_compare_store(existing_id)
        if row:
            stores.append(row)
            return row
    ok, _message, row = compare_stores_db.create_compare_store(
        store_name=label,
        website_url=f'https://{host}' if host else '',
    )
    if ok and row:
        stores.append(row)
        return row
    retry_id = compare_stores_db.find_store_id_by_name(label)
    if retry_id:
        row = compare_stores_db.get_compare_store(retry_id)
        if row:
            stores.append(row)
            return row
    return {'store_id': None, 'store_name': label}


def _search_terms(identity: Dict[str, Any]) -> List[str]:
    query = _clean_text(identity.get('search_query') or identity.get('product_name'))
    barcode = _clean_text(identity.get('barcode'))
    terms: List[str] = []
    if query:
        terms.extend(
            (
                f'{query} Qatar buy',
                f'{query} site:.qa',
                f'{query} Doha store',
                f'{query} site:snoonu.com',
                f'{query} site:virginmegastore.qa',
            )
        )
    return terms[:5]


def _web_find_product_urls(identity: Dict[str, Any]) -> List[Tuple[int, str]]:
    query = _clean_text(identity.get('search_query') or identity.get('product_name'))
    barcode = _clean_text(identity.get('barcode'))
    ranked: List[Tuple[int, str]] = []
    seen_url: set[str] = set()
    seen_host: set[str] = set()

    if query:
        try:
            snoonu = page_import_svc.resolve_snoonu_product_url(query or barcode)
        except Exception:
            snoonu = ''
        if (
            snoonu
            and '/product/' in snoonu
            and _looks_like_product_url(snoonu)
            and _is_qatar_store_url(snoonu)
        ):
            ranked.append((_score_url(snoonu, query or barcode) + 3, snoonu))
            seen_url.add(snoonu.rstrip('/').lower())
            seen_host.add(_host_of(snoonu))

    terms = _search_terms(identity)
    web_hits: List[str] = []
    if terms:
        workers = min(4, len(terms))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for found in pool.map(_web_search_urls, terms):
                web_hits.extend(found)
    for url in web_hits:
        if not _looks_like_product_url(url) or not _is_qatar_store_url(url):
            continue
        key = url.rstrip('/').lower()
        host = _host_of(url)
        if key in seen_url or host in seen_host:
            continue
        path = (urlparse(url).path or '').lower()
        score = _score_url(url, query or barcode)
        has_product_path = any(hint in path for hint in _PRODUCT_PATH_HINTS)
        if score < 2 or (not has_product_path and score < 4):
            continue
        seen_url.add(key)
        seen_host.add(host)
        ranked.append((score, url))
        if len(ranked) >= _MAX_CANDIDATES:
            break
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[:_MAX_CANDIDATES]


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }.get(ext, 'image/jpeg')


def _read_local_image(image_url: str) -> Tuple[Optional[bytes], str]:
    value = str(image_url or '').strip()
    if not value or 'placeholder' in value.lower():
        return None, ''
    if '/media/files/' in value:
        filename = value.split('/media/files/')[-1].split('?')[0]
        path = media_svc.resolve_file_path(filename)
        if path and path.is_file():
            return path.read_bytes()[:_MAX_IMAGE_BYTES], _mime_for_path(path)
    rel = ''
    if value.startswith('/static/'):
        rel = value[len('/static/'):].split('?')[0]
    elif value.startswith('/') and not value.startswith('/media/'):
        rel = value.lstrip('/').split('?')[0]
    elif '://' not in value and not value.startswith('data:'):
        rel = value.lstrip('/').split('?')[0]
    if rel and '..' not in rel:
        roots = [Path('/var/www/mamahub/static')]
        try:
            from nexa_http import current_app

            folder = getattr(current_app, 'static_folder', None)
            if folder:
                roots.insert(0, Path(folder))
        except Exception:
            pass
        for root in roots:
            path = (root / rel).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                continue
            if path.is_file():
                return path.read_bytes()[:_MAX_IMAGE_BYTES], _mime_for_path(path)
    return None, ''


def _read_remote_image(image_url: str) -> Tuple[Optional[bytes], str]:
    if not requests or not str(image_url or '').lower().startswith(('http://', 'https://')):
        return None, ''
    try:
        parsed = urlparse(image_url)
        if not parsed.hostname or not page_import_svc._host_is_public(parsed.hostname):
            return None, ''
        resp = requests.get(
            image_url,
            headers={'User-Agent': _UA, 'Accept': 'image/*,*/*;q=0.8'},
            timeout=_SEARCH_TIMEOUT,
            stream=True,
        )
        if resp.status_code >= 400:
            return None, ''
        data = resp.content[:_MAX_IMAGE_BYTES]
        mime = str(resp.headers.get('Content-Type') or 'image/jpeg').split(';', 1)[0].strip()
        if not mime.startswith('image/'):
            mime = 'image/jpeg'
        return data, mime
    except Exception:
        return None, ''


def _product_image_part(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    image_url = str(product.get('image_url') or '').strip()
    raw, mime = _read_local_image(image_url)
    if not raw:
        raw, mime = _read_remote_image(image_url)
    if not raw:
        return None
    b64 = base64.b64encode(raw).decode('ascii')
    return {'type': 'image_url', 'image_url': {'url': f'data:{mime or "image/jpeg"};base64,{b64}'}}


def _item_barcode(item_code: int) -> str:
    try:
        row = get_item_by_code(int(item_code), resolve_location_code()) or {}
    except Exception:
        return ''
    return _clean_text(row.get('manufacturerid') or row.get('MANUFACTURERID'))


def _fallback_identity(product: Dict[str, Any], barcode: str) -> Dict[str, Any]:
    name = _clean_text(product.get('item_name'))
    brand = _clean_text(product.get('brand_name'))
    query = default_search_name(item_name=name) or name
    if brand and brand.lower() not in query.lower():
        query = f'{brand} {query}'.strip()[:120]
    return {
        'brand': brand,
        'product_name': name,
        'search_query': query,
        'barcode': barcode,
        'source': 'name',
    }


def _identify_product(product: Dict[str, Any], barcode: str) -> Dict[str, Any]:
    fallback = _fallback_identity(product, barcode)
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key or not requests:
        return fallback
    image_part = _product_image_part(product)
    user_text = (
        'Identify this retail product so we can find the same item on other store websites. '
        f'ERP name: {fallback["product_name"] or "unknown"}. '
        f'Brand: {fallback["brand"] or "unknown"}. '
        f'Barcode: {barcode or "unknown"}. '
        'Reply JSON only: '
        '{"brand":"","product_name":"","search_query":"","barcode":"","color":"","pack":""}. '
        'search_query must be a short web-search phrase (brand + product + distinctive words). '
        'We will search Qatar stores only. '
        'Do not invent a barcode.'
    )
    content: List[Dict[str, Any]] = [{'type': 'text', 'text': user_text}]
    if image_part:
        content.append(image_part)
    try:
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': _openai_model(),
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {
                        'role': 'system',
                        'content': (
                            'You identify consumer products from a photo and ERP name. '
                            'Prefer visible packaging text. Keep search_query under 12 words.'
                        ),
                    },
                    {'role': 'user', 'content': content},
                ],
            },
            timeout=_VISION_TIMEOUT,
        )
        if resp.status_code >= 400:
            return fallback
        choices = (resp.json() or {}).get('choices') or []
        raw = str(((choices[0] or {}).get('message') or {}).get('content') or '').strip()
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            return fallback
        query = _clean_text(parsed.get('search_query') or parsed.get('product_name')) or fallback['search_query']
        found_barcode = _clean_text(parsed.get('barcode')) or barcode
        return {
            'brand': _clean_text(parsed.get('brand')) or fallback['brand'],
            'product_name': _clean_text(parsed.get('product_name')) or fallback['product_name'],
            'search_query': query,
            'barcode': found_barcode,
            'source': 'vision' if image_part else 'ai',
        }
    except Exception:
        return fallback


def find_compare_urls(item_code: int, search_query: str = '') -> Dict[str, Any]:
    """Return suggested competitor product URLs from the open web."""
    product = catalog_svc.get_product_for_edit(int(item_code))
    if not product:
        return {'ok': False, 'error': 'Product not found.', 'suggestions': []}
    if not requests:
        return {'ok': False, 'error': 'Web search is unavailable on this server.', 'suggestions': []}

    typed = default_search_name(item_name=search_query)
    if typed:
        identity = {
            'brand': _clean_text(product.get('brand_name')),
            'product_name': _clean_text(product.get('item_name')),
            'search_query': typed,
            'barcode': '',
            'source': 'typed',
        }
    else:
        barcode = _item_barcode(int(item_code))
        identity = _identify_product(product, barcode)
        identity['search_query'] = default_search_name(item_name=str(identity.get('search_query') or '')) or (
            default_search_name(product) or _clean_text(product.get('item_name'))
        )
    existing = {
        str(entry.get('url') or '').rstrip('/').lower()
        for entry in web_meta_svc.clean_compare_urls(product.get('compare_urls'))
    }
    stores = list(compare_stores_db.list_compare_stores(active_only=False))
    ranked = _web_find_product_urls(identity)
    found: List[Dict[str, Any]] = []
    for score, url in ranked:
        key = url.rstrip('/').lower()
        if key in existing:
            continue
        store = _match_or_create_store(url, stores)
        found.append(
            {
                'store_id': store.get('store_id'),
                'store_name': store.get('store_name') or _store_label_from_host(_host_of(url)),
                'url': url,
                'title': identity.get('search_query') or product.get('item_name') or '',
                'confidence': 'high' if score >= 6 else 'medium',
            }
        )
        if len(found) >= _MAX_CANDIDATES:
            break
    if not found:
        return {
            'ok': False,
            'error': (
                f'No Qatar store pages found for “{identity.get("search_query") or product.get("item_name")}”. '
                'Edit the product name above and search again, or paste a Qatar product URL.'
            ),
            'identified': identity,
            'suggestions': [],
        }
    return {
        'ok': True,
        'message': f'Found {len(found)} Qatar store URL{"s" if len(found) != 1 else ""}.',
        'identified': identity,
        'suggestions': found,
        'openai': openai_configured(),
        'used_image': identity.get('source') == 'vision',
    }
