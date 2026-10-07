"""Find catalog toys from a customer photo using OpenAI vision."""
from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from storefront_backend.services import catalog as catalog_svc

_MAX_BYTES = 4 * 1024 * 1024
_ALLOWED = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}
_TIMEOUT = 35


def openai_configured() -> bool:
    return bool((os.environ.get('OPENAI_API_KEY') or '').strip())


def _model() -> str:
    return (
        (os.environ.get('OPENAI_VISION_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
        or 'gpt-4o-mini'
    )


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').split()).strip()


def _parse_identity(raw: str) -> Dict[str, Any]:
    text = (raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)
        text = re.sub(r'\s*```$', '', text)
    try:
        parsed: Any = json.loads(text) if text else {}
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.S)
        try:
            parsed = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            parsed = {}
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _shrink_image(content: bytes, mime: str) -> Tuple[bytes, str]:
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        image = image.convert('RGB')
        image.thumbnail((1024, 1024))
        buf = io.BytesIO()
        image.save(buf, format='JPEG', quality=78)
        return buf.getvalue(), 'image/jpeg'
    except Exception:
        return content, mime


def _identify(content: bytes, mime: str) -> Dict[str, str]:
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise ValueError('Photo search is not configured.')
    payload, used_mime = _shrink_image(content, mime)
    encoded = base64.b64encode(payload).decode('ascii')
    data_url = f'data:{used_mime};base64,{encoded}'
    resp = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': _model(),
            'temperature': 0.1,
            'response_format': {'type': 'json_object'},
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You identify toys and children’s products from a customer photo '
                        'so we can search a toy store catalog. Reply JSON only.'
                    ),
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                'What toy or kids product is in this photo? '
                                'Reply JSON: {"search_query":"","brand":"","keywords":[]}. '
                                'search_query must be 3 to 8 catalog words (brand + toy type) and never empty. '
                                'Ignore backgrounds, people, and hands. If unsure, guess the toy type.'
                            ),
                        },
                        {'type': 'image_url', 'image_url': {'url': data_url, 'detail': 'low'}},
                    ],
                },
            ],
        },
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise ValueError('Could not recognize that photo.')
    choices = (resp.json() or {}).get('choices') or []
    raw = str(((choices[0] or {}).get('message') or {}).get('content') or '').strip()
    parsed = _parse_identity(raw)
    query = _clean(parsed.get('search_query') or parsed.get('product_name'))
    keywords = parsed.get('keywords') if isinstance(parsed.get('keywords'), list) else []
    extra = [_clean(word) for word in keywords if _clean(word)]
    brand = _clean(parsed.get('brand'))
    if not query:
        query = ' '.join(extra[:4]) or brand
    if not query:
        raise ValueError('Could not recognize that photo.')
    query = re.sub(r'[^A-Za-z0-9\u0600-\u06FF &+-]+', ' ', query)
    query = ' '.join(query.split())[:80]
    return {'search_query': query, 'brand': brand}


def _search(query: str, location_code: Optional[int] = None) -> List[Dict[str, Any]]:
    items, _ = catalog_svc.list_products(
        location_code=location_code,
        search=query,
        page=1,
        page_size=12,
        sort='itemname',
        order='asc',
    )
    return items


def search_by_image(
    content: bytes,
    mime: str,
    *,
    location_code: Optional[int] = None,
) -> Dict[str, Any]:
    if not content:
        raise ValueError('Please choose a photo.')
    if len(content) > _MAX_BYTES:
        raise ValueError('Photo is too large. Use a picture under 4 MB.')
    kind = (mime or 'image/jpeg').split(';')[0].strip().lower()
    if kind not in _ALLOWED:
        raise ValueError('Please upload a JPG, PNG, or WebP photo.')
    if not openai_configured():
        raise ValueError('Photo search is not available right now.')

    identity = _identify(content, kind)
    query = identity['search_query']
    items = _search(query, location_code)
    if len(items) < 3 and identity.get('brand'):
        branded = _search(f'{identity["brand"]} {query}', location_code)
        if len(branded) > len(items):
            items = branded
            query = f'{identity["brand"]} {identity["search_query"]}'.strip()
    return {
        'query': query,
        'brand': identity.get('brand') or '',
        'products': items,
    }
