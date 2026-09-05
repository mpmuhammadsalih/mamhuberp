"""CMS page admin services for the ecommerce addon."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import cms_db

PAGE_TYPES = ('STATIC', 'FAQ', 'CONTACT')


def _empty_form() -> Dict[str, Any]:
    return {
        'cms_page_id': '',
        'page_code': '',
        'page_title': '',
        'slug': '',
        'page_type': 'STATIC',
        'content_html': '',
        'meta_json': '{}',
        'meta_description': '',
        'sort_order': 0,
        'is_published': True,
    }


def page_to_form(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = row.get('meta') or {}
    return {
        'cms_page_id': row.get('cms_page_id') or '',
        'page_code': row.get('page_code') or '',
        'page_title': row.get('page_title') or '',
        'slug': row.get('slug') or '',
        'page_type': row.get('page_type') or 'STATIC',
        'content_html': row.get('content_html') or '',
        'meta_json': json.dumps(meta, indent=2, ensure_ascii=False) if meta else '{}',
        'meta_description': row.get('meta_description') or '',
        'sort_order': row.get('sort_order') or 0,
        'is_published': row.get('is_published', True),
    }


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.strip().lower())
    return slug.strip('-')[:120]


def list_cms_page() -> Dict[str, Any]:
    cms_db.ensure_default_pages()
    pages, warning = cms_db.list_pages()
    return {
        'pages': pages,
        'warning': warning,
        'tables_ready': cms_db.cms_table_ready(),
    }


def get_create_form() -> Dict[str, Any]:
    return _empty_form()


def get_edit_form(cms_page_id: int) -> Optional[Dict[str, Any]]:
    row = cms_db.get_page(cms_page_id)
    return page_to_form(row) if row else None


def save_page(form: Dict[str, Any]) -> Tuple[bool, str]:
    cms_db.ensure_default_pages()
    slug = (form.get('slug') or '').strip().lower() or _slugify(form.get('page_title') or '')
    page_code = (form.get('page_code') or '').strip().upper() or slug.replace('-', '_').upper()[:80]
    page_type = (form.get('page_type') or 'STATIC').strip().upper()
    if page_type not in PAGE_TYPES:
        page_type = 'STATIC'

    meta_raw = (form.get('meta_json') or '').strip() or '{}'
    try:
        json.loads(meta_raw)
    except json.JSONDecodeError:
        return False, 'Structured data (meta JSON) is invalid.'

    payload = {
        'cms_page_id': form.get('cms_page_id') or None,
        'page_code': page_code,
        'page_title': (form.get('page_title') or '').strip(),
        'slug': slug,
        'page_type': page_type,
        'content_html': form.get('content_html') or '',
        'meta_json': meta_raw,
        'meta_description': (form.get('meta_description') or '').strip() or None,
        'sort_order': form.get('sort_order') or 0,
        'is_published': form.get('is_published') in (True, '1', 'on', 'true', 1),
    }
    ok, message, _ = cms_db.upsert_page(payload)
    return ok, message
