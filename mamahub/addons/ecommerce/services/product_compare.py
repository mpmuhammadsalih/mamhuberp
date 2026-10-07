"""Compare this MamaHub product against related store URLs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from addons.ecommerce import compare_stores_db
from addons.ecommerce.services import catalog as catalog_svc
from addons.ecommerce.services import product_page_import as page_import_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc

_MAX_COMPARE_URLS = 8
_DESC_PREVIEW = 280


def _host_label(page_url: str) -> str:
    host = (urlparse(page_url).hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    return host or 'Website'


def _as_price(value: Any) -> Optional[float]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _ours_row(product: Dict[str, Any]) -> Dict[str, Any]:
    offer = _as_price(product.get('offer_price'))
    retail = _as_price(product.get('retail_price'))
    price = offer or retail
    return {
        'ok': True,
        'is_ours': True,
        'source': 'MamaHub',
        'title': str(product.get('item_name') or '').strip(),
        'description': str(product.get('description_text') or '').strip()[:_DESC_PREVIEW],
        'image_url': product.get('image_url') or '',
        'price': price,
        'currency': 'QAR',
        'page_url': '',
        'error': '',
    }


def preview_compare_url(page_url: str, item_name: str = '', store_name: str = '') -> Dict[str, Any]:
    label = str(store_name or '').strip() or _host_label(page_url)
    try:
        resolved = page_import_svc._maybe_resolve_snoonu(page_url, item_name)
        extracted = page_import_svc.extract_product_page(resolved)
    except ValueError as exc:
        return {
            'ok': False,
            'is_ours': False,
            'source': label,
            'store_name': label,
            'title': '',
            'description': '',
            'image_url': '',
            'price': None,
            'currency': '',
            'page_url': page_url,
            'error': str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            'ok': False,
            'is_ours': False,
            'source': label,
            'store_name': label,
            'title': '',
            'description': '',
            'image_url': '',
            'price': None,
            'currency': '',
            'page_url': page_url,
            'error': f'Could not read that page. {exc}',
        }
    images = list(extracted.get('image_urls') or [])
    final_url = str(extracted.get('page_url') or page_url)
    source = str(store_name or '').strip() or _host_label(final_url)
    return {
        'ok': True,
        'is_ours': False,
        'source': source,
        'store_name': source,
        'title': str(extracted.get('title') or '').strip(),
        'description': str(extracted.get('description') or '').strip()[:_DESC_PREVIEW],
        'image_url': images[0] if images else '',
        'price': _as_price(extracted.get('price')),
        'currency': str(extracted.get('currency') or '').strip().upper() or '',
        'page_url': final_url,
        'error': '',
    }


def _mark_price_ranks(rows: List[Dict[str, Any]]) -> None:
    prices = [row['price'] for row in rows if row.get('ok') and row.get('price') is not None]
    if len(prices) < 2:
        return
    low = min(prices)
    high = max(prices)
    if low == high:
        return
    for row in rows:
        price = row.get('price')
        if not row.get('ok') or price is None:
            continue
        if price == low:
            row['price_rank'] = 'low'
        elif price == high:
            row['price_rank'] = 'high'


def compare_product(item_code: int, extra_entries: Optional[List[Any]] = None) -> Dict[str, Any]:
    product = catalog_svc.get_product_for_edit(int(item_code))
    if not product:
        return {'ok': False, 'error': 'Product not found.', 'rows': [], 'entries': []}

    saved = list(product.get('compare_urls') or [])
    entries = web_meta_svc.clean_compare_urls(saved if extra_entries is None else extra_entries)
    for entry in entries:
        store_id = entry.get('store_id')
        store = compare_stores_db.get_compare_store(int(store_id)) if store_id else None
        if store and store.get('store_name'):
            entry['store_name'] = store.get('store_name')
            entry['store_id'] = int(store.get('store_id') or 0) or None
        elif entry.get('store_name') and not store_id:
            matched = compare_stores_db.find_store_id_by_name(str(entry.get('store_name') or ''))
            if matched:
                entry['store_id'] = matched
                named = compare_stores_db.get_compare_store(matched)
                if named and named.get('store_name'):
                    entry['store_name'] = named.get('store_name')
    item_name = str(product.get('item_name') or '')
    rows: List[Dict[str, Any]] = [_ours_row(product)]
    fetched: List[Optional[Dict[str, Any]]] = [None] * len(entries)
    if entries:
        workers = min(4, len(entries))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    preview_compare_url,
                    entry.get('url') or '',
                    item_name,
                    entry.get('store_name') or '',
                ): index
                for index, entry in enumerate(entries)
            }
            for future in as_completed(futures):
                fetched[futures[future]] = future.result()
    rows.extend(row for row in fetched if row)
    _mark_price_ranks(rows)

    prices = [row['price'] for row in rows if row.get('ok') and row.get('price') is not None]
    return {
        'ok': True,
        'product': product,
        'entries': entries,
        'urls': [entry.get('url') or '' for entry in entries],
        'rows': rows,
        'lowest_price': min(prices) if prices else None,
        'highest_price': max(prices) if prices else None,
    }


def save_compare_urls(item_code: int, entries: List[Any]) -> tuple[bool, str]:
    cleaned = web_meta_svc.clean_compare_urls(entries)
    return web_meta_svc.save_product_web_meta(
        int(item_code),
        compare_urls=cleaned,
        touch_compare_urls=True,
    )
