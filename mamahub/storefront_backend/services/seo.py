"""Sitemap and SEO helpers for the storefront."""
from __future__ import annotations

import os
from typing import List, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring

from db import get_items_list

from storefront_backend.deps import resolve_location_code
from storefront_backend.services import cms as cms_svc


def _storefront_base_url() -> str:
    return (os.getenv('STOREFRONT_BASE_URL') or os.getenv('PUBLIC_SITE_URL') or 'https://www.mamahub.store').rstrip('/')


def _url_elem(parent: Element, loc: str, *, changefreq: str, priority: str) -> None:
    url = SubElement(parent, 'url')
    SubElement(url, 'loc').text = loc
    SubElement(url, 'changefreq').text = changefreq
    SubElement(url, 'priority').text = priority


def build_sitemap_xml(base_url: str | None = None) -> str:
    base = (base_url or _storefront_base_url()).rstrip('/')
    urlset = Element(
        'urlset',
        xmlns='http://www.sitemaps.org/schemas/sitemap/0.9',
    )

    static_routes: List[Tuple[str, str, str]] = [
        ('/', 'daily', '1.0'),
        ('/products', 'daily', '0.9'),
        ('/offers', 'daily', '0.85'),
        ('/new-arrivals', 'daily', '0.85'),
        ('/best-sellers', 'daily', '0.85'),
        ('/featured', 'weekly', '0.8'),
        ('/gift-finder', 'weekly', '0.7'),
    ]
    for path, freq, priority in static_routes:
        _url_elem(urlset, f'{base}{path}', changefreq=freq, priority=priority)

    for page in cms_svc.list_pages():
        slug = str(page.get('slug') or '').strip()
        if not slug:
            continue
        _url_elem(urlset, f'{base}/page/{slug}', changefreq='monthly', priority='0.5')

    loc = resolve_location_code()
    hidden_codes = []
    try:
        from addons.ecommerce.services import product_web_meta as web_meta_svc

        hidden_codes = web_meta_svc.hidden_item_codes()
    except Exception:  # noqa: BLE001
        hidden_codes = []
    page_num = 1
    page_size = 500
    total = 1
    while (page_num - 1) * page_size < total:
        rows, total = get_items_list(
            location_code=loc,
            page=page_num,
            items_per_page=page_size,
            exclude_item_codes=hidden_codes or None,
        )
        if not rows:
            break
        for row in rows:
            code = row.get('itemcode') or row.get('ITEMCODE')
            if code is None:
                continue
            _url_elem(
                urlset,
                f'{base}/products/{int(code)}',
                changefreq='weekly',
                priority='0.65',
            )
        page_num += 1
        if page_num > 40:
            break

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(urlset, encoding='unicode')
