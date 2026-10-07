"""Import description, features, and images from a public product page URL."""
from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from addons.ecommerce import media_db
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import product_images as product_images_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from addons.ecommerce.services.common import resolve_location_code
from db import ensure_itemmaster_image_path_column, get_item_by_code, set_item_image_path

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
_HTML_TIMEOUT_SEC = 20
_MAX_HTML_BYTES = 2 * 1024 * 1024
_MAX_IMAGES = 16
_MAX_IMAGE_CANDIDATES = 24
_DESC_MAX = 2000
_SPECS_MAX = 3500
_BLOCKED_HOSTS = {
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    '::1',
    'metadata.google.internal',
}
_SKIP_IMAGE_PARTS = (
    'sprite',
    'pixel',
    'tracking',
    'favicon',
    'logo.',
    '/logo',
    'icon-',
    'icons/',
    'badge',
    'payment',
    '1x1',
    'blank.gif',
    'placeholder',
    'spinner',
    'loading.',
    'data:image/svg',
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_SCRIPT_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_META_RE = re.compile(
    r'<meta\b([^>]+)>',
    re.I,
)
_ATTR_RE = re.compile(
    r'''([^\s=]+)\s*=\s*(['"])(.*?)\2''',
    re.I | re.S,
)
_IMG_SRC_RE = re.compile(
    r'<img\b[^>]+(?:src|data-src|data-zoom-image|data-large|data-full-image)\s*=\s*[\'"]([^\'"]+)[\'"]',
    re.I,
)
_IMG_TAG_RE = re.compile(r'<img\b([^>]+)>', re.I)
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=[\'"]og:image(?::secure_url)?[\'"][^>]+content=[\'"]([^\'"]+)[\'"]',
    re.I,
)
_OG_IMAGE_REV_RE = re.compile(
    r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+(?:property|name)=[\'"]og:image(?::secure_url)?[\'"]',
    re.I,
)
_GALLERY_CHUNK_RE = re.compile(
    r'<(?:div|section|ul|ol|figure)\b[^>]*(?:class|id|data-section)=[\'"][^\'"]*'
    r'(?:product[-_]?(?:gallery|media|images|photos|thumbs|slideshow)|'
    r'woocommerce-product-gallery|pdp[-_]?gallery|gallery-viewer|'
    r'media-gallery|product__media|slick-track|flickity|swiper-wrapper)'
    r'[^\'"]*[\'"][^>]*>',
    re.I,
)
_SRCSET_URL_RE = re.compile(r'([^\s,]+)\s+\d+[wx]', re.I)
_HTTP_IMAGE_RE = re.compile(
    r'''(?:https?:)?//[^\s'"<>\\]+?\.(?:jpe?g|png|webp)(?:\?[^\s'"<>\\]*)?''',
    re.I,
)
_RELATED_HINT_RE = re.compile(
    r'related|recommend|you-may|also-like|upsell|cross-sell|recently-viewed|'
    r'cart-drawer|minicart',
    re.I,
)
_SIZE_SUFFIX_RE = re.compile(
    r'_(?:pico|icon|thumb|small|compact|medium|large|grande|master|\d{2,4}x\d{0,4})'
    r'(?=\.(?:jpe?g|png|webp|gif)$)',
    re.I,
)
_STRIP_IMAGE_QUERY = {
    'width',
    'height',
    'w',
    'h',
    'quality',
    'q',
    'crop',
    'fit',
    'auto',
    'format',
    'ixlib',
    'dpr',
}
_JSON_IMAGE_KEYS = {
    'image',
    'images',
    'img',
    'src',
    'url',
    'contenturl',
    'zoom',
    'zoom_image',
    'full',
    'full_size',
    'featured_image',
    'preview_image',
    'thumbnail',
    'thumb',
    'hires',
    'large',
}
_LI_RE = re.compile(r'<li\b[^>]*>(.*?)</li>', re.I | re.S)
_TR_RE = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.I | re.S)
_CELL_RE = re.compile(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', re.I | re.S)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _title_case_words(value: Any) -> str:
    text = ' '.join(str(value or '').split())
    if not text:
        return ''
    parts = []
    for word in text.split(' '):
        bits = []
        for part in word.split('-'):
            if not part:
                bits.append(part)
                continue
            bits.append(part[:1].upper() + part[1:].lower())
        parts.append('-'.join(bits))
    return ' '.join(parts)


def _is_mostly_upper(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for ch in letters if ch.isupper()) >= len(letters) * 0.7


def _clean_text(value: Any, *, limit: Optional[int] = None) -> str:
    text = html.unescape(_TAG_RE.sub(' ', str(value or '')))
    text = _WS_RE.sub(' ', text).strip()
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + '…'
    return text


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _host_is_public(host: str) -> bool:
    name = (host or '').strip().lower().rstrip('.')
    if not name or name in _BLOCKED_HOSTS or name.endswith('.local') or name.endswith('.internal'):
        return False
    try:
        infos = socket.getaddrinfo(name, None)
    except socket.gaierror:
        return False
    saw_ip = False
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        saw_ip = True
        if _is_blocked_ip(ip):
            return False
    return saw_ip


def _normalize_page_url(raw: str) -> str:
    value = html.unescape(str(raw or '').strip())
    if not value:
        raise ValueError('Paste a product page URL first.')
    if value.startswith('//'):
        value = f'https:{value}'
    if not re.match(r'^https?://', value, re.I):
        value = f'https://{value}'
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('URL must start with http:// or https://')
    if not parsed.hostname:
        raise ValueError('URL is missing a website name.')
    if not _host_is_public(parsed.hostname):
        raise ValueError('That URL cannot be opened from the server.')
    return value


_SNOONU_ID_RE = re.compile(r'^[a-f0-9]{20,24}$', re.I)
_SNOONU_LINK_RE = re.compile(
    r'https://(?:www\.)?snoonu\.com/product/([a-z0-9-]+)/([a-f0-9]{20,24})',
    re.I,
)


def snoonu_slug(name: str) -> str:
    text = str(name or '').strip().lower()
    text = text.replace('&', ' and ')
    text = re.sub(r'\.', '', text)
    text = re.sub(r"['’]", '', text)
    text = re.sub(r'\s*-\s*', '---', text)
    text = re.sub(r'[^a-z0-9-]+', '-', text)
    text = re.sub(r'-{4,}', '---', text)
    return text.strip('-')


def resolve_snoonu_product_url(product_name: str, *, hint_url: str = '') -> str:
    """Build https://snoonu.com/product/<slug> and resolve the live product page if needed."""
    parsed_hint = urlparse(str(hint_url or '').strip())
    hint_parts = [p for p in parsed_hint.path.split('/') if p]
    slug = ''
    if len(hint_parts) >= 2 and hint_parts[0].lower() == 'product':
        slug = hint_parts[1].strip().lower()
        if len(hint_parts) >= 3 and _SNOONU_ID_RE.match(hint_parts[2]):
            return f'https://snoonu.com/product/{slug}/{hint_parts[2]}'
    slug = slug or snoonu_slug(product_name)
    if not slug:
        raise ValueError('Enter a product name first.')
    query_name = str(product_name or '').strip() or slug.replace('-', ' ')
    if not requests:
        raise ValueError('Could not look up that Snoonu product. Paste the full product link.')
    try:
        resp = requests.post(
            'https://html.duckduckgo.com/html/',
            data={'q': f'site:snoonu.com/product {query_name}'},
            headers={'User-Agent': _UA, 'Accept': 'text/html'},
            timeout=_HTML_TIMEOUT_SEC,
        )
        html_text = html.unescape(resp.text or '')
    except Exception as exc:
        raise ValueError('Could not look up that Snoonu product. Paste the full product link.') from exc
    matches = _SNOONU_LINK_RE.findall(html_text)
    if not matches:
        raise ValueError(
            'Could not find that item name on Snoonu. Paste the full product link '
            '(it must include the ID after the name).'
        )
    for found_slug, pid in matches:
        found = found_slug.lower()
        if found == slug or found.startswith(slug) or slug.startswith(found):
            return f'https://snoonu.com/product/{found}/{pid}'
    found_slug, pid = matches[0]
    return f'https://snoonu.com/product/{found_slug}/{pid}'


def _maybe_resolve_snoonu(page_url: str, item_name: str = '') -> str:
    parsed = urlparse(str(page_url or '').strip())
    host = (parsed.hostname or '').lower()
    if host not in ('snoonu.com', 'www.snoonu.com'):
        return page_url
    return resolve_snoonu_product_url(item_name, hint_url=page_url)


def _fetch_bytes(url: str, *, accept: str) -> Tuple[bytes, str]:
    if not requests:
        raise ValueError('Page import requires the requests library (pip install requests).')
    resp = requests.get(
        url,
        headers={
            'User-Agent': _UA,
            'Accept': accept,
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
        },
        timeout=_HTML_TIMEOUT_SEC,
        allow_redirects=True,
        stream=True,
    )
    final = str(resp.url or url)
    parsed = urlparse(final)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or not _host_is_public(parsed.hostname):
        raise ValueError('The page redirected to an address that cannot be opened.')
    if resp.status_code >= 400:
        raise ValueError(f'The page returned HTTP {resp.status_code}.')
    chunks: List[bytes] = []
    total = 0
    for chunk in resp.iter_content(64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_HTML_BYTES:
            break
        chunks.append(chunk)
    return (b''.join(chunks), final)


def _absolute_url(base: str, href: str) -> str:
    cleaned = html.unescape(str(href or '').strip())
    if not cleaned or cleaned.startswith('data:'):
        return ''
    if cleaned.startswith('//'):
        cleaned = f'https:{cleaned}'
    return urljoin(base, cleaned)


def _meta_map(html_text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for match in _META_RE.finditer(html_text):
        attrs = {k.lower(): html.unescape(v) for k, _q, v in _ATTR_RE.findall(match.group(1))}
        key = attrs.get('property') or attrs.get('name') or attrs.get('itemprop') or ''
        content = attrs.get('content') or attrs.get('value') or ''
        key = key.strip().lower()
        content = content.strip()
        if key and content and key not in out:
            out[key] = content
    return out


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_money(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return amount if amount > 0 else None
    text = str(value).replace('\u00a0', ' ').replace(',', '').strip()
    if not text:
        return None
    match = re.search(r'(\d+(?:\.\d{1,3})?)', text)
    if not match:
        return None
    amount = float(match.group(1))
    return amount if amount > 0 else None


def _price_from_offers(offers: Any) -> Tuple[Optional[float], str]:
    currency = ''
    chosen: Optional[float] = None
    for offer in _as_list(offers):
        if not isinstance(offer, dict):
            amount = _parse_money(offer)
            if amount and (chosen is None or amount < chosen):
                chosen = amount
            continue
        currency = currency or str(
            offer.get('priceCurrency') or offer.get('pricecurrency') or ''
        ).strip().upper()
        amount = _parse_money(offer.get('lowPrice') or offer.get('price') or offer.get('highPrice'))
        if amount and (chosen is None or amount < chosen):
            chosen = amount
    return chosen, currency[:8]


def _price_from_html(html_text: str, product: Dict[str, Any], meta: Dict[str, str]) -> Tuple[Optional[float], str]:
    price, currency = _price_from_offers(product.get('offers') or product.get('offer'))
    if not currency:
        currency = str(
            meta.get('product:price:currency')
            or meta.get('og:price:currency')
            or meta.get('pricecurrency')
            or ''
        ).strip().upper()
    if price is None:
        for key in ('product:price:amount', 'og:price:amount', 'price'):
            price = _parse_money(meta.get(key))
            if price:
                break
    if price is None:
        itemprop = re.search(
            r'itemprop=[\'"]price[\'"][^>]*content=[\'"]([^\'"]+)[\'"]|'
            r'content=[\'"]([^\'"]+)[\'"][^>]*itemprop=[\'"]price[\'"]',
            html_text,
            flags=re.I,
        )
        if itemprop:
            price = _parse_money(itemprop.group(1) or itemprop.group(2))
    return price, currency[:8]


def _shopify_price(payload: Dict[str, Any]) -> Tuple[Optional[float], str]:
    raw = payload.get('price')
    if raw is None:
        raw = payload.get('price_min')
    amount = _parse_money(raw)
    if amount is None:
        return None, ''
    if isinstance(raw, (int, float)) and float(raw) >= 100 and float(raw) == int(float(raw)):
        amount = round(amount / 100.0, 2)
    return amount, str(payload.get('currency') or '').strip().upper()[:8]


def _type_names(node: Any) -> List[str]:
    if not isinstance(node, dict):
        return []
    raw = node.get('@type') or node.get('type')
    names = []
    for item in _as_list(raw):
        names.append(str(item).split('/')[-1].strip().lower())
    return names


def _walk_jsonld(node: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_jsonld(item))
        return found
    if not isinstance(node, dict):
        return found
    if 'product' in _type_names(node):
        found.append(node)
    for key in ('@graph', 'mainEntity', 'itemListElement', 'hasVariant', 'isVariantOf'):
        if key in node:
            found.extend(_walk_jsonld(node.get(key)))
    return found


def _parse_jsonld_products(html_text: str) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    for match in _SCRIPT_JSON_RE.finditer(html_text):
        raw = match.group(1).strip()
        if not raw:
            continue
        raw = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        products.extend(_walk_jsonld(data))
    return products


def _image_urls_from_value(value: Any, base: str) -> List[str]:
    urls: List[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            candidate = item.get('url') or item.get('contentUrl') or item.get('@id')
        else:
            candidate = item
        abs_url = _absolute_url(base, str(candidate or ''))
        if abs_url:
            urls.append(abs_url)
    return urls


def _specs_from_product(product: Dict[str, Any]) -> List[str]:
    lines: List[str] = []

    def add(label: str, value: Any) -> None:
        text = _clean_text(value)
        name = _clean_text(label)
        if not text or not name:
            return
        if text.lower() in {name.lower(), 'true', 'false'}:
            return
        line = f'{name}: {text}'
        if line not in lines:
            lines.append(line)

    for key, label in (
        ('brand', 'Brand'),
        ('color', 'Color'),
        ('material', 'Material'),
        ('sku', 'SKU'),
        ('mpn', 'MPN'),
        ('gtin13', 'GTIN'),
        ('gtin12', 'GTIN'),
        ('gtin', 'GTIN'),
        ('model', 'Model'),
        ('weight', 'Weight'),
        ('size', 'Size'),
    ):
        raw = product.get(key)
        if isinstance(raw, dict):
            raw = raw.get('name') or raw.get('value')
        add(label, raw)

    for prop in _as_list(product.get('additionalProperty')):
        if not isinstance(prop, dict):
            continue
        add(prop.get('name') or prop.get('propertyID'), prop.get('value'))
    return lines


_FEATURE_JSON_KEYS = {
    'features',
    'key_features',
    'keyfeatures',
    'highlights',
    'feature_list',
    'featurelist',
    'product_features',
    'productfeatures',
}


def _split_feature_bullets(text: Any) -> List[str]:
    raw = html.unescape(_TAG_RE.sub('\n', str(text or '')))
    raw = re.sub(r'[•●▪►]', '\n', raw)
    raw = re.sub(r'(?<=\S)\s+[-–]\s+(?=[A-Z0-9])', '\n', raw)
    out: List[str] = []
    for line in raw.splitlines():
        item = _WS_RE.sub(' ', line).strip(' \t-•●▪')
        if (
            8 <= len(item) <= 220
            and item.lower() not in {'key features', 'features', 'highlights'}
            and '{' not in item
            and 'window.' not in item.lower()
        ):
            if item not in out:
                out.append(item)
    return out


def _key_features_from_text(text: str) -> List[str]:
    blob = _clean_text(text)
    if not blob:
        return []
    match = re.search(
        r'key\s*features?\s*[:\-–]?\s*(.+?)(?=(?:specifications|what.?s included|dimensions|packaging includes|the (?:product|yoyos|set) come)|$)',
        blob,
        flags=re.I,
    )
    if not match:
        return []
    chunk = match.group(1)
    items = _split_feature_bullets(chunk)
    if len(items) >= 2 or re.search(r'[•●▪►]', chunk):
        return items
    return []


def _features_from_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _key_features_from_text(value) or _split_feature_bullets(value)
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            if isinstance(item, str):
                cleaned = _clean_text(item)
                if 8 <= len(cleaned) <= 220 and cleaned not in out:
                    out.append(cleaned)
                continue
            if isinstance(item, dict):
                text = (
                    item.get('value')
                    or item.get('text')
                    or item.get('name')
                    or item.get('title')
                    or item.get('description')
                )
                if isinstance(text, (dict, list)) or text is None:
                    continue
                cleaned = _clean_text(text)
                if 8 <= len(cleaned) <= 220 and cleaned not in out:
                    out.append(cleaned)
        return out
    if isinstance(value, dict):
        out: List[str] = []
        for key, raw in value.items():
            if str(key).strip().lower().replace('-', '_') in _FEATURE_JSON_KEYS:
                for item in _features_from_value(raw):
                    if item not in out:
                        out.append(item)
        return out
    return []


def _features_from_product(product: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ('feature', 'features', 'highlight', 'highlights'):
        for item in _features_from_value(product.get(key)):
            if item not in out:
                out.append(item)
    return out


def _features_from_embedded_json(html_text: str) -> List[str]:
    out: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        for key, raw in node.items():
            key_l = str(key).strip().lower().replace('-', '_')
            if key_l in _FEATURE_JSON_KEYS:
                for item in _features_from_value(raw):
                    if item not in out:
                        out.append(item)
            elif isinstance(raw, (dict, list)):
                walk(raw)

    for match in re.finditer(r'<script\b[^>]*>(.*?)</script>', html_text, flags=re.I | re.S):
        raw = match.group(1).strip()
        if not raw or len(raw) < 20:
            continue
        raw = re.sub(r'^\s*(?:window\.)?\w+\s*=\s*', '', raw).rstrip().rstrip(';')
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        walk(data)
    return out[:20]


def _html_without_scripts(html_text: str) -> str:
    return re.sub(r'<script\b[^>]*>.*?</script>', ' ', html_text or '', flags=re.I | re.S)


def _key_features_from_html(html_text: str, description: str = '') -> List[str]:
    features: List[str] = []
    visible = _html_without_scripts(html_text)

    def add_all(items: List[str]) -> None:
        for item in items:
            if item not in features:
                features.append(item)

    add_all(_key_features_from_text(description))

    heading_lists = re.findall(
        r'(?:key\s*features?|product\s*features?|highlights?)[^<]{0,120}</(?:h[1-6]|strong|b|p|span|div)>\s*'
        r'<(?:ul|ol)\b[^>]*>(.*?)</(?:ul|ol)>',
        visible,
        flags=re.I | re.S,
    )
    for chunk in heading_lists:
        for li in _LI_RE.findall(chunk):
            add_all(_split_feature_bullets(li) or ([_clean_text(li)] if 8 <= len(_clean_text(li)) <= 220 else []))

    after_heading = re.findall(
        r'(?:key\s*features?|product\s*features?|highlights?)\s*[:\-–]?\s*'
        r'</(?:h[1-6]|strong|b|p|span|div|dt)>'
        r'(.*?)(?=<(?:h[1-6]|section|footer)\b|$)',
        visible[:80000],
        flags=re.I | re.S,
    )
    for chunk in after_heading[:3]:
        lis = _LI_RE.findall(chunk)
        if lis:
            for li in lis[:20]:
                add_all(
                    _split_feature_bullets(li)
                    or ([_clean_text(li)] if 8 <= len(_clean_text(li)) <= 220 else [])
                )
            continue
        for para in re.findall(r'<p\b[^>]*>(.*?)</p>', chunk, flags=re.I | re.S)[:20]:
            add_all(
                _split_feature_bullets(para)
                or ([_clean_text(para)] if 8 <= len(_clean_text(para)) <= 220 else [])
            )

    class_lists = re.findall(
        r'<(?:ul|ol)\b[^>]*(?:class|id)=[\'"][^\'"]*(?:key[-_]?feature|feature[-_]?list|highlight)[^\'"]*[\'"][^>]*>(.*?)</(?:ul|ol)>',
        visible,
        flags=re.I | re.S,
    )
    for chunk in class_lists:
        for li in _LI_RE.findall(chunk):
            text = _clean_text(li)
            if 8 <= len(text) <= 220:
                add_all([text])
    if len(features) < 2:
        add_all(_key_features_from_text(_clean_text(visible[:25000])))
    return features[:20]


_DESC_SECTION_CUT_RE = re.compile(
    r'(?:^|(?<=[.!?])\s+|[\s•●▪]+)'
    r'(?:'
    r'key\s*features?|'
    r'product\s*features?|'
    r'highlights|'
    r'what[\'’]?s\s+included|'
    r'technical\s+(?:details|specifications)|'
    r'product\s+details|'
    r'specifications?'
    r')'
    r'(?:\s*[:\-–]|\s+(?=[A-Z][A-Za-z][A-Za-z0-9 /&]{0,30}\s*:))',
    re.I,
)
_SPEC_LABELS = (
    'age',
    'ages',
    'battery',
    'brand',
    'capacity',
    'color',
    'colour',
    'contents',
    'country of origin',
    'diameter',
    'dimensions',
    'gender',
    'gtin',
    'height',
    'includes',
    'length',
    'made in',
    'material',
    'model',
    'mpn',
    'origin',
    'pack',
    'packing',
    'piece count',
    'pieces',
    'product type',
    'quantity',
    'set',
    'size',
    'sku',
    'theme',
    'type',
    'voltage',
    'volume',
    'warranty',
    'weight',
    'width',
)
_SPEC_LABEL_RE = re.compile(
    r'(?:^|(?<=\s))('
    + '|'.join(re.escape(label) for label in sorted(_SPEC_LABELS, key=len, reverse=True))
    + r')\s*:',
    re.I,
)


def _specs_from_description_text(text: str) -> List[str]:
    blob = _clean_text(text)
    if not blob:
        return []
    match = re.search(
        r'(?:specifications?|technical\s+(?:details|specifications)|product\s+details)\s*[:\-–]?\s*(.+)$',
        blob,
        flags=re.I,
    )
    if not match:
        return []
    chunk = match.group(1).strip()
    marks = list(_SPEC_LABEL_RE.finditer(chunk))
    lines: List[str] = []
    for index, mark in enumerate(marks):
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(chunk)
        _add_spec_line(lines, mark.group(1), chunk[start:end])
    return lines


def _strip_features_from_description(
    description: str,
    features: Optional[List[str]] = None,
    spec_lines: Optional[List[str]] = None,
) -> str:
    """Keep product copy only; features and specs belong in Specifications."""
    text = str(description or '').strip()
    if not text:
        return ''
    cut = _DESC_SECTION_CUT_RE.search(text)
    if cut:
        text = text[: cut.start()].strip()
    leftovers: List[str] = []
    for item in list(features or []) + list(spec_lines or []):
        cleaned = _clean_text(item)
        if cleaned:
            leftovers.append(cleaned)
        if ':' in cleaned:
            value = cleaned.split(':', 1)[1].strip()
            if len(value) >= 8:
                leftovers.append(value)
    for item in leftovers:
        if len(item) < 12:
            continue
        text = re.sub(re.escape(item), ' ', text, flags=re.I)
    text = re.sub(r'[•●▪►]+', ' ', text)
    text = re.sub(
        r'(?:key\s*features?|product\s*features?|highlights|specifications?|what[\'’]?s\s+included)\s*[:\-–]?\s*$',
        '',
        text,
        flags=re.I,
    )
    text = _WS_RE.sub(' ', text).strip(' \t-•●▪,;:')
    text = re.sub(r'\s+([.!?])', r'\1', text)
    if len(text) < 8:
        return ''
    return text[:_DESC_MAX]


def _format_specifications(features: List[str], spec_lines: List[str]) -> str:
    feature_set = {item.lower() for item in features}
    extra = [line for line in spec_lines if line.lower() not in feature_set]
    blocks: List[str] = []
    if features:
        blocks.append('Key features:')
        blocks.extend(f'• {item}' for item in features)
    if extra:
        if blocks:
            blocks.append('')
        blocks.extend(extra)
    return '\n'.join(blocks)[:_SPECS_MAX]


def _add_spec_line(lines: List[str], label: Any, value: Any) -> None:
    name = _clean_text(label)
    text = _clean_text(value)
    if not name or not text:
        return
    if text.lower() in {name.lower(), 'true', 'false'}:
        return
    if len(name) > 80 or len(text) > 240:
        return
    line = f'{name}: {text}'
    if line not in lines:
        lines.append(line)


def _specs_from_tables(html_text: str) -> List[str]:
    lines: List[str] = []
    for table in re.findall(r'<table\b[^>]*>(.*?)</table>', html_text, flags=re.I | re.S):
        for row in _TR_RE.findall(table):
            cells = [_clean_text(cell) for cell in _CELL_RE.findall(row)]
            cells = [c for c in cells if c]
            if len(cells) == 2:
                _add_spec_line(lines, cells[0], cells[1])
    return lines


def _specs_from_html(html_text: str) -> List[str]:
    lines: List[str] = []
    feature_chunks = re.findall(
        r'<(?:ul|ol)\b[^>]*(?:class|id)=[\'"][^\'"]*'
        r'(?:feature|highlight|bullet|spec|benefit|detail|attribute)'
        r'[^\'"]*[\'"][^>]*>(.*?)</(?:ul|ol)>',
        html_text,
        flags=re.I | re.S,
    )
    for chunk in feature_chunks:
        for li in _LI_RE.findall(chunk):
            text = _clean_text(li)
            if 3 <= len(text) <= 220 and text not in lines:
                lines.append(text)

    for table_line in _specs_from_tables(html_text):
        if table_line not in lines:
            lines.append(table_line)

    for dl in re.findall(r'<dl\b[^>]*>(.*?)</dl>', html_text, flags=re.I | re.S):
        dts = [_clean_text(x) for x in re.findall(r'<dt\b[^>]*>(.*?)</dt>', dl, flags=re.I | re.S)]
        dds = [_clean_text(x) for x in re.findall(r'<dd\b[^>]*>(.*?)</dd>', dl, flags=re.I | re.S)]
        for name, text in zip(dts, dds):
            _add_spec_line(lines, name, text)

    for match in re.finditer(
        r'<[^>]+class=[\'"][^\'"]*(?:woocommerce-product-attributes-item|'
        r'product-attribute|spec-item|spec-row|attribute-item)[^\'"]*[\'"][^>]*>'
        r'(.*?)</(?:div|tr|li|section)>',
        html_text,
        flags=re.I | re.S,
    ):
        chunk = match.group(1)
        label = re.search(
            r'<(?:th|dt|span|div|strong)\b[^>]*(?:class|id)=[\'"][^\'"]*(?:label|name|title)[^\'"]*[\'"][^>]*>(.*?)</',
            chunk,
            flags=re.I | re.S,
        )
        value = re.search(
            r'<(?:td|dd|span|div)\b[^>]*(?:class|id)=[\'"][^\'"]*(?:value|content)[^\'"]*[\'"][^>]*>(.*?)</',
            chunk,
            flags=re.I | re.S,
        )
        if label and value:
            _add_spec_line(lines, label.group(1), value.group(1))
    return lines[:60]


def _specs_from_embedded_json(html_text: str) -> List[str]:
    lines: List[str] = []
    keys = {
        'specifications',
        'specs',
        'attributes',
        'additional_attributes',
        'additionalproperty',
        'additional_properties',
        'product_attributes',
        'technical_specifications',
        'metafields',
        'options',
        'features',
        'key_features',
        'keyfeatures',
        'highlights',
    }

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        label = node.get('name') or node.get('label') or node.get('title') or node.get('key')
        value = node.get('value') or node.get('content')
        if label and value is not None and not isinstance(value, (dict, list)):
            _add_spec_line(lines, label, value)
        for key, raw in node.items():
            key_l = str(key).strip().lower()
            if key_l in keys:
                walk(raw)
                continue
            if (
                isinstance(raw, list)
                and raw
                and isinstance(raw[0], dict)
                and (raw[0].get('label') or raw[0].get('name'))
                and (raw[0].get('value') is not None or raw[0].get('content') is not None)
            ):
                walk(raw)

    for match in re.finditer(r'<script\b[^>]*>(.*?)</script>', html_text, flags=re.I | re.S):
        raw = match.group(1).strip()
        if not raw or len(raw) < 20:
            continue
        raw = re.sub(r'^\s*window\.\w+\s*=\s*', '', raw).rstrip().rstrip(';')
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        walk(data)
    return lines[:60]


def _looks_like_image(url: str) -> bool:
    low = url.lower()
    if any(part in low for part in _SKIP_IMAGE_PARTS):
        return False
    parsed = urlparse(low)
    if parsed.scheme not in ('http', 'https'):
        return False
    path = parsed.path
    if any(path.endswith(ext) for ext in ('.svg', '.ico', '.gif')) and 'product' not in low:
        return False
    return True


def _upgrade_image_url(url: str) -> str:
    parsed = urlparse(url)
    path = _SIZE_SUFFIX_RE.sub('', parsed.path)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _STRIP_IMAGE_QUERY
    ]
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, urlencode(query), ''))


def _dedupe_urls(urls: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for url in urls:
        upgraded = _upgrade_image_url(url)
        key = upgraded.split('?')[0].rstrip('/').lower()
        if not upgraded or key in seen or not _looks_like_image(upgraded):
            continue
        seen.add(key)
        out.append(upgraded)
    return out


def _in_related_context(html_text: str, pos: int) -> bool:
    return bool(_RELATED_HINT_RE.search(html_text[max(0, pos - 500) : pos]))


def _walk_json_images(node: Any, base: str) -> List[str]:
    urls: List[str] = []
    if isinstance(node, list):
        for item in node:
            urls.extend(_walk_json_images(item, base))
        return urls
    if isinstance(node, str):
        if '.' in node and any(node.lower().endswith(ext) or f'.{ext}?' in node.lower() for ext in ('jpg', 'jpeg', 'png', 'webp')):
            abs_url = _absolute_url(base, node)
            if abs_url:
                urls.append(abs_url)
        return urls
    if not isinstance(node, dict):
        return urls
    for key, value in node.items():
        if str(key).strip().lower() in _JSON_IMAGE_KEYS or isinstance(value, (dict, list)):
            urls.extend(_walk_json_images(value, base))
    return urls


def _embedded_json_images(html_text: str, page_url: str) -> List[str]:
    urls: List[str] = []
    for match in re.finditer(
        r'<script\b[^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    ):
        raw = match.group(1).strip()
        if not raw or len(raw) < 20:
            continue
        raw = re.sub(r'^\s*window\.\w+\s*=\s*', '', raw)
        raw = raw.rstrip().rstrip(';')
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            for found in _HTTP_IMAGE_RE.findall(raw):
                abs_url = _absolute_url(page_url, found)
                if abs_url:
                    urls.append(abs_url)
            continue
        urls.extend(_walk_json_images(data, page_url))
    return urls


def _page_content_images(html_text: str, page_url: str) -> List[str]:
    urls: List[str] = []
    for img in _IMG_TAG_RE.finditer(html_text):
        if _in_related_context(html_text, img.start()):
            continue
        urls.extend(_urls_from_img_attrs(img.group(1), page_url))
    for match in re.finditer(
        r'data-(?:image|zoom-image|large_image|full-image|zoom_image)=[\'"]([^\'"]+)[\'"]',
        html_text,
        flags=re.I,
    ):
        if _in_related_context(html_text, match.start()):
            continue
        abs_url = _absolute_url(page_url, match.group(1))
        if abs_url:
            urls.append(abs_url)
    return urls


def _urls_from_srcset(value: str, base: str) -> List[str]:
    urls: List[str] = []
    for match in _SRCSET_URL_RE.finditer(str(value or '')):
        abs_url = _absolute_url(base, match.group(1))
        if abs_url:
            urls.append(abs_url)
    if not urls:
        first = str(value or '').split(',')[0].strip().split(' ')[0]
        abs_url = _absolute_url(base, first)
        if abs_url:
            urls.append(abs_url)
    return urls


def _urls_from_img_attrs(attr_html: str, base: str) -> List[str]:
    attrs = {k.lower(): html.unescape(v) for k, _q, v in _ATTR_RE.findall(attr_html)}
    urls: List[str] = []
    for key in (
        'data-zoom-image',
        'data-large',
        'data-full-image',
        'data-zoom',
        'data-src',
        'src',
    ):
        abs_url = _absolute_url(base, attrs.get(key) or '')
        if abs_url:
            urls.append(abs_url)
    for key in ('srcset', 'data-srcset'):
        urls.extend(_urls_from_srcset(attrs.get(key) or '', base))
    return urls


def _og_image_urls(html_text: str, page_url: str, meta: Dict[str, str]) -> List[str]:
    urls: List[str] = []
    for key in ('og:image', 'og:image:secure_url', 'twitter:image', 'twitter:image:src'):
        abs_url = _absolute_url(page_url, meta.get(key) or '')
        if abs_url:
            urls.append(abs_url)
    for match in list(_OG_IMAGE_RE.finditer(html_text)) + list(_OG_IMAGE_REV_RE.finditer(html_text)):
        abs_url = _absolute_url(page_url, match.group(1))
        if abs_url:
            urls.append(abs_url)
    return urls


def _same_folder_images(official: List[str], extras: List[str]) -> List[str]:
    """Keep extras only when they sit in the same folder as this product's photos."""
    base = _dedupe_urls(official)
    extra = _dedupe_urls(extras)
    if not base:
        return extra
    folders = {url.split('?')[0].rsplit('/', 1)[0].lower() for url in base}
    kept = list(base)
    seen = {url.split('?')[0].rstrip('/').lower() for url in kept}
    for url in extra:
        folder = url.split('?')[0].rsplit('/', 1)[0].lower()
        key = url.split('?')[0].rstrip('/').lower()
        if folder in folders and key not in seen:
            kept.append(url)
            seen.add(key)
    return kept


def _gallery_dom_images(html_text: str, page_url: str) -> List[str]:
    """Extra photos from this product page's gallery markup, not related-item tiles."""
    urls: List[str] = []
    for match in _GALLERY_CHUNK_RE.finditer(html_text):
        start = match.start()
        chunk = html_text[start : start + 8000]
        cut = _RELATED_HINT_RE.search(chunk[len(match.group(0)) :])
        if cut:
            chunk = chunk[: len(match.group(0)) + cut.start()]
        for img in _IMG_TAG_RE.finditer(chunk):
            if _in_related_context(html_text, start + img.start()):
                continue
            urls.extend(_urls_from_img_attrs(img.group(1), page_url))
        for href_match in re.finditer(
            r'<a\b[^>]+href=[\'"]([^\'"]+\.(?:jpe?g|png|webp)(?:\?[^\'"]*)?)[\'"]',
            chunk,
            flags=re.I,
        ):
            if _in_related_context(html_text, start + href_match.start()):
                continue
            abs_url = _absolute_url(page_url, href_match.group(1))
            if abs_url:
                urls.append(abs_url)
    return urls


def _next_data_product_images(html_text: str, page_url: str) -> List[str]:
    """Read product.images from Next.js __NEXT_DATA__ (Snoonu and similar)."""
    match = _NEXT_DATA_RE.search(html_text or '')
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    urls: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        images = node.get('images')
        if isinstance(images, list) and images:
            found: List[str] = []
            for item in images:
                raw = item
                if isinstance(item, dict):
                    raw = item.get('url') or item.get('src') or item.get('image') or ''
                abs_url = _absolute_url(page_url, str(raw or ''))
                if abs_url and _looks_like_image(abs_url):
                    found.append(abs_url)
            if found:
                urls.extend(found)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(data)
    return urls


def _snoonu_next_payload(html_text: str, page_url: str) -> Dict[str, Any]:
    """Read the live Snoonu product object from Next.js __NEXT_DATA__."""
    parsed = urlparse(page_url)
    host = (parsed.hostname or '').lower()
    if host not in ('snoonu.com', 'www.snoonu.com'):
        return {}
    match = _NEXT_DATA_RE.search(html_text or '')
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    parts = [p for p in parsed.path.split('/') if p]
    product_id = parts[-1] if parts and _SNOONU_ID_RE.match(parts[-1]) else ''
    best: Dict[str, Any] = {}

    def consider(node: Dict[str, Any]) -> None:
        nonlocal best
        name = node.get('name') or node.get('title') or node.get('productName')
        images = node.get('images') or node.get('galleryImages') or node.get('photos')
        desc = node.get('description') or node.get('longDescription') or node.get('body')
        nid = str(node.get('id') or node.get('_id') or node.get('productId') or '')
        score = 0
        if product_id and nid == product_id:
            score += 5
        if name:
            score += 1
        if desc:
            score += 1
        if isinstance(images, list) and images:
            score += 2
        if score > int(best.get('_score') or 0):
            best = dict(node)
            best['_score'] = score

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        keys = set(str(k).lower() for k in node.keys())
        if {'name', 'images'} <= keys or {'title', 'description'} <= keys or 'productid' in keys:
            consider(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(data)
    if not best:
        return {}
    images = []
    for raw in _as_list(best.get('images') or best.get('galleryImages') or best.get('photos')):
        if isinstance(raw, dict):
            raw = raw.get('url') or raw.get('src') or raw.get('image') or raw.get('path') or ''
        abs_url = _absolute_url(page_url, str(raw or ''))
        if abs_url:
            images.append(abs_url)
    price = _parse_money(
        best.get('salePrice')
        or best.get('finalPrice')
        or best.get('price')
        or best.get('sellingPrice')
    )
    specs = _specs_from_product(best)
    return {
        'title': _clean_text(best.get('name') or best.get('title') or best.get('productName'), limit=200),
        'description': _clean_text(
            best.get('description') or best.get('longDescription') or best.get('body'),
            limit=_DESC_MAX,
        ),
        'image_urls': _dedupe_urls(images)[:_MAX_IMAGE_CANDIDATES],
        'price': price,
        'currency': str(best.get('currency') or 'QAR').strip().upper()[:8],
        'specifications': _format_specifications([], specs),
    }


def _extract_from_html(html_text: str, page_url: str) -> Dict[str, Any]:
    products = _parse_jsonld_products(html_text)
    product = products[0] if products else {}
    meta = _meta_map(html_text)

    description = _clean_text(
        product.get('description')
        or meta.get('og:description')
        or meta.get('twitter:description')
        or meta.get('description'),
        limit=_DESC_MAX,
    )
    meta_description = _clean_text(
        meta.get('og:description')
        or meta.get('twitter:description')
        or meta.get('description')
        or product.get('description'),
        limit=web_meta_svc._SEO_DESC_MAX,
    )
    title = _clean_text(
        product.get('name') or meta.get('og:title') or meta.get('twitter:title') or meta.get('title'),
        limit=200,
    )
    price, currency = _price_from_html(html_text, product, meta)

    spec_lines = _specs_from_product(product)
    for line in (
        _specs_from_html(html_text)
        + _specs_from_embedded_json(html_text)
        + _specs_from_description_text(description)
    ):
        if line not in spec_lines:
            spec_lines.append(line)
    features = _key_features_from_html(html_text, description)
    for item in _features_from_product(product):
        if item not in features:
            features.append(item)
    if len(features) < 2:
        for item in _features_from_embedded_json(html_text):
            if item not in features:
                features.append(item)
    features = features[:20]
    if not features and not spec_lines:
        for li in _LI_RE.findall(html_text)[:40]:
            text = _clean_text(li)
            if 12 <= len(text) <= 180 and text not in spec_lines:
                spec_lines.append(text)
    description = _strip_features_from_description(description, features, spec_lines)

    product_images = _image_urls_from_value(product.get('image'), page_url)
    og_images = _og_image_urls(html_text, page_url, meta)
    gallery_images = _gallery_dom_images(html_text, page_url)
    next_images = _next_data_product_images(html_text, page_url)
    snoonu = _snoonu_next_payload(html_text, page_url)
    if snoonu.get('title') and not title:
        title = snoonu['title']
    if snoonu.get('description') and (not description or len(snoonu['description']) > len(description)):
        description = snoonu['description']
    if snoonu.get('price') and price is None:
        price = snoonu['price']
    if snoonu.get('currency') and not currency:
        currency = snoonu['currency']
    if snoonu.get('specifications'):
        extra_specs = [line for line in str(snoonu['specifications']).splitlines() if line.strip()]
        for line in extra_specs:
            if line not in spec_lines:
                spec_lines.append(line)
    if snoonu.get('image_urls'):
        next_images = list(snoonu.get('image_urls') or []) + list(next_images or [])
    if next_images:
        images = next_images
    elif product_images:
        images = _same_folder_images(product_images, gallery_images)
    elif gallery_images:
        images = gallery_images
    else:
        images = og_images[:1]
    return {
        'title': title,
        'description': description,
        'meta_description': meta_description,
        'specifications': _format_specifications(features, spec_lines),
        'image_urls': _dedupe_urls(images)[:_MAX_IMAGE_CANDIDATES],
        'price': price,
        'currency': currency,
    }


def _extract_shopify_js(page_url: str) -> Optional[Dict[str, Any]]:
    parsed = urlparse(page_url)
    path = parsed.path.rstrip('/')
    path_l = path.lower()
    if path.endswith('.js') or not any(part in path_l for part in ('/products/', '/product/')):
        return None
    js_url = f'{parsed.scheme}://{parsed.netloc}{path}.js'
    try:
        data, _final = _fetch_bytes(js_url, accept='application/json,text/javascript,*/*;q=0.8')
        payload = json.loads(data.decode('utf-8', errors='replace'))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    images = []
    for raw in _as_list(payload.get('images')) + _as_list((payload.get('featured_image'),)):
        if isinstance(raw, dict):
            raw = raw.get('src') or raw.get('url') or ''
        images.append(_absolute_url(page_url, str(raw or '')))
    for media in _as_list(payload.get('media')):
        if not isinstance(media, dict):
            continue
        preview = media.get('preview_image') if isinstance(media.get('preview_image'), dict) else {}
        raw = media.get('src') or preview.get('src') or media.get('url') or ''
        images.append(_absolute_url(page_url, str(raw or '')))
    specs = []
    for option in _as_list(payload.get('options')):
        if isinstance(option, str) and option.strip():
            specs.append(option.strip())
        elif isinstance(option, dict) and option.get('name'):
            values = option.get('values') or []
            if values:
                specs.append(f"{option.get('name')}: {', '.join(str(v) for v in values[:6])}")
    desc_html = str(payload.get('description') or '')
    if desc_html:
        for line in _specs_from_html(desc_html):
            if line not in specs:
                specs.append(line)
    shopify_desc = _clean_text(payload.get('description'), limit=_DESC_MAX)
    for line in _specs_from_description_text(shopify_desc):
        if line not in specs:
            specs.append(line)
    features = _key_features_from_html(desc_html, shopify_desc)
    for item in _features_from_value(payload.get('features') or payload.get('highlights')):
        if item not in features:
            features.append(item)
    shopify_desc = _strip_features_from_description(shopify_desc, features, specs)
    shopify_price, shopify_currency = _shopify_price(payload)
    return {
        'title': _clean_text(payload.get('title'), limit=200),
        'description': shopify_desc,
        'specifications': _format_specifications(features, specs),
        'image_urls': _dedupe_urls(images)[:_MAX_IMAGE_CANDIDATES],
        'price': shopify_price,
        'currency': shopify_currency,
    }


def extract_product_page(page_url: str) -> Dict[str, Any]:
    url = _normalize_page_url(page_url)
    html_bytes, final_url = _fetch_bytes(url, accept='text/html,application/xhtml+xml;q=0.9,*/*;q=0.8')
    html_text = html_bytes.decode('utf-8', errors='replace')
    extracted = _extract_from_html(html_text, final_url)
    shopify = _extract_shopify_js(final_url)
    if shopify:
        if not extracted.get('description') and shopify.get('description'):
            extracted['description'] = shopify['description']
        if shopify.get('specifications'):
            merged: List[str] = []
            for block in (extracted.get('specifications'), shopify.get('specifications')):
                for line in str(block or '').splitlines():
                    text = line.strip()
                    if text and text not in merged:
                        merged.append(text)
            extracted['specifications'] = '\n'.join(merged)[:_SPECS_MAX]
        if shopify.get('image_urls'):
            extracted['image_urls'] = list(shopify.get('image_urls') or [])
        if not extracted.get('title'):
            extracted['title'] = shopify.get('title') or ''
        if extracted.get('price') is None and shopify.get('price') is not None:
            extracted['price'] = shopify.get('price')
        if not extracted.get('currency') and shopify.get('currency'):
            extracted['currency'] = shopify.get('currency')
    extracted['description'] = _strip_features_from_description(
        extracted.get('description') or ''
    )
    extracted['page_url'] = final_url
    host = (urlparse(final_url).hostname or '').lower()
    if host in ('snoonu.com', 'www.snoonu.com'):
        try:
            from addons.ecommerce.services.snoonu import _fetch_snoonu_api, snoonu_product_id

            api = _fetch_snoonu_api(snoonu_product_id(final_url) or snoonu_product_id(url))
        except Exception:
            api = None
        if api:
            if api.get('title') and not extracted.get('title'):
                extracted['title'] = api['title']
            if api.get('description') and (
                not extracted.get('description')
                or len(str(api.get('description') or '')) > len(str(extracted.get('description') or ''))
            ):
                extracted['description'] = api['description']
            api_images = list(api.get('image_urls') or [])
            if api_images:
                extracted['image_urls'] = _dedupe_urls(api_images + list(extracted.get('image_urls') or []))
    return extracted


def _delete_gallery_file(image_url: str) -> None:
    raw = str(image_url or '').strip()
    prefix = '/media/files/'
    if raw.startswith(prefix):
        name = raw[len(prefix) :].split('?', 1)[0]
        if name and '/' not in name and '..' not in name:
            path = media_svc.uploads_dir() / name
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
        return
    product_images_svc._delete_local_image(raw)


def _clear_existing_product_images(
    item_code: int,
    location_code: int,
    item: Dict[str, Any],
    *,
    keep_main_path: str = '',
) -> None:
    """Remove this product's previous photos after the new main image is saved."""
    existing = str(item.get('image_path') or item.get('IMAGE_PATH') or '').strip()
    keep = str(keep_main_path or '').strip()
    if existing and existing != keep:
        product_images_svc._delete_local_image(existing)

    if not media_db.media_table_ready():
        return
    rows, _ = media_db.list_media(placement='product', active_only=False)
    for row in rows:
        if str(row.get('ref_key') or '').strip() != str(item_code):
            continue
        if not row.get('is_active'):
            continue
        media_id = int(row.get('media_id') or 0)
        if media_id:
            media_db.deactivate_media(media_id)
        _delete_gallery_file(row.get('image_url') or '')


def _add_gallery_path(item_code: int, image_url: str, sort_order: int) -> Optional[Dict[str, Any]]:
    payload = {
        'placement': 'product',
        'ref_key': str(item_code),
        'title': f'Product {item_code} gallery',
        'subtitle': None,
        'image_url': image_url,
        'link_url': None,
        'alt_text': f'Product {item_code} photo',
        'sort_order': sort_order,
        'is_active': True,
        'meta': {},
    }
    ok, _msg, row = media_db.upsert_media(payload)
    if not ok or not row:
        return None
    from addons.ecommerce.services import catalog as catalog_svc

    return {
        'media_id': row.get('media_id'),
        'image_url': catalog_svc._gallery_admin_url(row.get('image_url')),
        'sort_order': row.get('sort_order') or sort_order,
    }


def import_from_page_url(
    *,
    item_code: int,
    page_url: str,
    location_code: Optional[int] = None,
    save_images: bool = True,
) -> Dict[str, Any]:
    loc = int(location_code or resolve_location_code())
    ic = int(item_code)
    if ic <= 0:
        return {'ok': False, 'error': 'Invalid item code.'}
    item = get_item_by_code(ic, loc)
    if not item:
        return {'ok': False, 'error': f'Item {ic} not found for this location.'}

    item_name_hint = str(
        item.get('itemname') or item.get('ITEMNAME') or item.get('name') or ''
    ).strip()
    try:
        page_url = _maybe_resolve_snoonu(page_url, item_name_hint)
        extracted = extract_product_page(page_url)
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'Could not read that page. {exc}'}

    description = extracted.get('description') or ''
    specifications = extracted.get('specifications') or ''
    fetched_name = str(extracted.get('title') or '').strip()
    if fetched_name and _is_mostly_upper(fetched_name):
        fetched_name = _title_case_words(fetched_name)
    item_name = fetched_name or str(
        item.get('itemname')
        or item.get('ITEMNAME')
        or item.get('name')
        or ''
    ).strip()
    page_title = fetched_name or item_name
    if page_title and (_is_mostly_upper(page_title) or not fetched_name):
        page_title = _title_case_words(page_title)
    seo_title = web_meta_svc.auto_seo_title(page_title)
    seo_description = web_meta_svc.auto_seo_description(
        item_name=item_name or extracted.get('title') or '',
        description=extracted.get('meta_description') or description,
        category_name=str(
            item.get('categoryname')
            or item.get('CATEGORYNAME')
            or item.get('category_name')
            or ''
        ).strip(),
        price=item.get('retailprice') or item.get('RETAILPRICE') or 0,
    )
    saved_page_url = str(extracted.get('page_url') or page_url or '').strip()
    if saved_page_url:
        web_meta_svc.save_product_web_meta(
            ic,
            import_page_url=saved_page_url,
            touch_import_page_url=True,
        )
    if seo_title or seo_description:
        web_meta_svc.save_product_web_meta(
            ic,
            seo_title=seo_title,
            seo_description=seo_description,
            touch_seo=True,
        )
    if specifications:
        web_meta_svc.save_product_web_meta(
            ic,
            specifications=specifications,
            touch_specs=True,
        )
    if description:
        from addons.ecommerce.services import product_edit as product_edit_svc

        product_edit_svc.set_item_description_text(
            ic,
            description,
            location_code=loc,
        )
    image_urls = list(extracted.get('image_urls') or [])
    if not save_images and not description and not specifications and not fetched_name:
        return {
            'ok': False,
            'error': 'No product name, description, or specifications were found on that page.',
            'page_url': extracted.get('page_url'),
        }
    if save_images and not description and not specifications and not image_urls and not fetched_name:
        return {
            'ok': False,
            'error': 'No product name, description, features, or images were found on that page.',
            'page_url': extracted.get('page_url'),
        }

    saved_main = None
    gallery: List[Dict[str, Any]] = []
    image_errors: List[str] = []
    if save_images and image_urls:
        ensure_itemmaster_image_path_column()
        downloaded: List[Tuple[bytes, str]] = []
        page_ref = str(extracted.get('page_url') or page_url or '')
        for image_url in image_urls[:_MAX_IMAGES]:
            try:
                downloaded.append(product_images_svc._download_image(image_url, referer=page_ref))
            except Exception as exc:  # noqa: BLE001
                image_errors.append(str(exc))

        if downloaded:
            first_data, first_ext = downloaded[0]
            try:
                rel_path = product_images_svc._save_item_image_bytes(
                    first_data, first_ext, location_code=loc, item_code=ic
                )
                ok, db_err = set_item_image_path(ic, loc, rel_path)
                if not ok:
                    ok, db_err = set_item_image_path(ic, loc, rel_path)
                from addons.ecommerce.services import product_edit as product_edit_svc

                preview = product_edit_svc.product_image_public_url(rel_path) or f'/static/{rel_path.lstrip("/")}'
                saved_main = preview
                if ok:
                    _clear_existing_product_images(ic, loc, item, keep_main_path=rel_path)
                else:
                    image_errors.append(db_err or 'Could not save main image path.')
            except Exception as exc:  # noqa: BLE001
                image_errors.append(str(exc))

            if downloaded[1:] and media_db.media_table_ready():
                sort_order = 0
                for data, ext in downloaded[1:]:
                    try:
                        ok, _msg, path = media_svc.save_bytes(data, ext, stem=f'product-{ic}')
                        if not ok or not path:
                            continue
                        sort_order += 1
                        saved = _add_gallery_path(ic, path, sort_order)
                        if saved:
                            gallery.append(saved)
                    except Exception as exc:  # noqa: BLE001
                        image_errors.append(str(exc))
                        continue

    bits = []
    if fetched_name:
        bits.append('product name')
    if description:
        bits.append('description')
    if seo_title:
        bits.append('page title')
    if seo_description:
        bits.append('meta description')
    if specifications:
        bits.append(f'{len(specifications.splitlines())} features')
    if saved_main:
        bits.append('main image')
    if gallery:
        bits.append(f'{len(gallery)} gallery photo{"s" if len(gallery) != 1 else ""}')
    message = 'Imported ' + ', '.join(bits) + '. Review the fields, then Save product.'
    if not save_images:
        message = (
            'Imported '
            + ', '.join(bits or ['details'])
            + '. Existing photos were left unchanged. Review the fields, then Save product.'
        )
    elif saved_main or gallery:
        message = (
            'Imported '
            + ', '.join(bits)
            + '. Existing photos were replaced. Review the fields, then Save product.'
        )
    if image_errors and not saved_main and not gallery:
        detail = image_errors[0] if image_errors else 'unknown error'
        message = (
            'Found text, but images could not be saved. '
            f'{detail} Existing photos were left unchanged. Description and features were filled — review and Save.'
        )

    return {
        'ok': True,
        'message': message,
        'item_code': ic,
        'page_url': extracted.get('page_url'),
        'source_title': extracted.get('title') or '',
        'item_name': fetched_name or '',
        'description': description,
        'seo_title': seo_title,
        'seo_description': seo_description,
        'specifications': specifications,
        'image_url': saved_main,
        'gallery_images': gallery,
        'found_image_count': len(image_urls),
        'images_saved': bool(save_images and (saved_main or gallery)),
        'image_errors': image_errors[:5],
    }
