"""MH_CMS_PAGE queries for the ecommerce addon."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce.cms_content import DEFAULT_CMS_PAGES
from addons.ecommerce.schema_bootstrap import ensure_cms_schema
from db import _get_connection, _safe_rows, _table_exists

CMS_TABLE = 'MH_CMS_PAGE'
CONTACT_TABLE = 'MH_CONTACT_INQUIRY'


def cms_table_ready() -> bool:
    if _table_exists(CMS_TABLE):
        return True
    try:
        ensure_cms_schema()
    except Exception:
        return False
    return _table_exists(CMS_TABLE)


def _table_missing_message() -> str:
    return (
        'MH_CMS_PAGE table is not installed in this database. '
        'Run MamaHub schema script sql/02_tables/14_mh_reviews_cms_notifications.sql on the tenant DB.'
    )


def _parse_meta(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _map_row(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = _parse_meta(row.pop('meta_json', None))
    return {
        **row,
        'meta': meta,
        'is_published': int(row.get('is_published') or 0) == 1,
    }


def list_pages(*, published_only: bool = False) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not cms_table_ready():
        return [], _table_missing_message()

    where = ['1=1']
    if published_only:
        where.append('IS_PUBLISHED = 1')

    rows = _safe_rows(
        f"""
        SELECT
            CMS_PAGE_ID AS cms_page_id,
            PAGE_CODE AS page_code,
            PAGE_TITLE AS page_title,
            SLUG AS slug,
            PAGE_TYPE AS page_type,
            META_JSON AS meta_json,
            META_DESCRIPTION AS meta_description,
            IS_PUBLISHED AS is_published,
            SORT_ORDER AS sort_order,
            CREATED_AT AS created_at,
            MODIFIED_AT AS modified_at
        FROM MH_CMS_PAGE
        WHERE {' AND '.join(where)}
        ORDER BY SORT_ORDER, PAGE_TITLE
        """,
        {},
    )
    return [_map_row(dict(row)) for row in rows], None


def get_page(cms_page_id: int) -> Optional[Dict[str, Any]]:
    if not cms_table_ready():
        return None
    rows = _safe_rows(
        """
        SELECT
            CMS_PAGE_ID AS cms_page_id,
            PAGE_CODE AS page_code,
            PAGE_TITLE AS page_title,
            SLUG AS slug,
            PAGE_TYPE AS page_type,
            CONTENT_HTML AS content_html,
            META_JSON AS meta_json,
            META_DESCRIPTION AS meta_description,
            IS_PUBLISHED AS is_published,
            SORT_ORDER AS sort_order,
            CREATED_AT AS created_at,
            MODIFIED_AT AS modified_at
        FROM MH_CMS_PAGE
        WHERE CMS_PAGE_ID = :cms_page_id
        """,
        {'cms_page_id': int(cms_page_id)},
    )
    return _map_row(dict(rows[0])) if rows else None


def get_page_by_slug(slug: str, *, published_only: bool = True) -> Optional[Dict[str, Any]]:
    if not cms_table_ready():
        return None
    where = ['LOWER(SLUG) = LOWER(:slug)']
    if published_only:
        where.append('IS_PUBLISHED = 1')
    rows = _safe_rows(
        f"""
        SELECT
            CMS_PAGE_ID AS cms_page_id,
            PAGE_CODE AS page_code,
            PAGE_TITLE AS page_title,
            SLUG AS slug,
            PAGE_TYPE AS page_type,
            CONTENT_HTML AS content_html,
            META_JSON AS meta_json,
            META_DESCRIPTION AS meta_description,
            IS_PUBLISHED AS is_published,
            SORT_ORDER AS sort_order,
            CREATED_AT AS created_at,
            MODIFIED_AT AS modified_at
        FROM MH_CMS_PAGE
        WHERE {' AND '.join(where)}
        """,
        {'slug': slug.strip()},
    )
    return _map_row(dict(rows[0])) if rows else None


def upsert_page(payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not cms_table_ready():
        return False, _table_missing_message(), None

    cms_page_id = payload.get('cms_page_id')
    slug = (payload.get('slug') or '').strip().lower()
    page_code = (payload.get('page_code') or '').strip().upper()
    page_title = (payload.get('page_title') or '').strip()
    if not slug or not page_code or not page_title:
        return False, 'Page code, title, and slug are required.', None

    meta_json = payload.get('meta_json')
    if isinstance(meta_json, dict):
        meta_json = json.dumps(meta_json, ensure_ascii=False)
    meta_json = (meta_json or '{}')[:32000]

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if cms_page_id:
                    cur.execute(
                        """
                        UPDATE MH_CMS_PAGE SET
                            PAGE_CODE = :page_code,
                            PAGE_TITLE = :page_title,
                            SLUG = :slug,
                            PAGE_TYPE = :page_type,
                            CONTENT_HTML = :content_html,
                            META_JSON = :meta_json,
                            META_DESCRIPTION = :meta_description,
                            IS_PUBLISHED = :is_published,
                            SORT_ORDER = :sort_order,
                            MODIFIED_AT = SYSTIMESTAMP
                        WHERE CMS_PAGE_ID = :cms_page_id
                        """,
                        {
                            'cms_page_id': int(cms_page_id),
                            'page_code': page_code,
                            'page_title': page_title,
                            'slug': slug,
                            'page_type': payload.get('page_type') or 'STATIC',
                            'content_html': payload.get('content_html') or '',
                            'meta_json': meta_json,
                            'meta_description': payload.get('meta_description'),
                            'is_published': 1 if payload.get('is_published', True) else 0,
                            'sort_order': int(payload.get('sort_order') or 0),
                        },
                    )
                    saved_id = int(cms_page_id)
                else:
                    cur.execute('SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL AS id FROM DUAL')
                    saved_id = int((cur.fetchone() or [0])[0])
                    cur.execute(
                        """
                        INSERT INTO MH_CMS_PAGE (
                            CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE,
                            CONTENT_HTML, META_JSON, META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER
                        ) VALUES (
                            :cms_page_id, :page_code, :page_title, :slug, :page_type,
                            :content_html, :meta_json, :meta_description, :is_published, :sort_order
                        )
                        """,
                        {
                            'cms_page_id': saved_id,
                            'page_code': page_code,
                            'page_title': page_title,
                            'slug': slug,
                            'page_type': payload.get('page_type') or 'STATIC',
                            'content_html': payload.get('content_html') or '',
                            'meta_json': meta_json,
                            'meta_description': payload.get('meta_description'),
                            'is_published': 1 if payload.get('is_published', True) else 0,
                            'sort_order': int(payload.get('sort_order') or 0),
                        },
                    )
            conn.commit()
        saved = get_page(saved_id)
        return True, 'CMS page saved', saved
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def ensure_default_pages() -> None:
    """Insert or upgrade default footer pages (idempotent)."""
    if not cms_table_ready():
        return
    for page in DEFAULT_CMS_PAGES:
        existing = _safe_rows(
            """
            SELECT CMS_PAGE_ID AS id, PAGE_TYPE AS page_type, META_JSON AS meta_json
            FROM MH_CMS_PAGE WHERE PAGE_CODE = :code
            """,
            {'code': page['page_code']},
        )
        if not existing:
            upsert_page({**page, 'is_published': True})
            continue
        row = existing[0]
        needs_upgrade = (
            not row.get('meta_json')
            or str(row.get('page_type') or '').upper() == 'STATIC'
            and str(page.get('page_type') or '').upper() in ('FAQ', 'CONTACT')
        )
        if needs_upgrade:
            upsert_page(
                {
                    **page,
                    'cms_page_id': row['id'],
                    'is_published': True,
                }
            )


def create_contact_inquiry(payload: Dict[str, Any]) -> Tuple[bool, str]:
    if not cms_table_ready():
        return False, _table_missing_message()

    name = (payload.get('name') or '').strip()
    email = (payload.get('email') or '').strip()
    subject = (payload.get('subject') or '').strip()
    message = (payload.get('message') or '').strip()
    if not name or not email or not message:
        return False, 'Name, email, and message are required.'
    if '@' not in email:
        return False, 'Please enter a valid email address.'

    if not _table_exists(CONTACT_TABLE):
        try:
            ensure_cms_schema()
        except Exception:
            return False, 'Contact inquiry table is not available.'

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT SEQ_MH_CONTACT_INQUIRY_ID.NEXTVAL AS id FROM DUAL')
                inquiry_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO MH_CONTACT_INQUIRY (
                        INQUIRY_ID, FULL_NAME, EMAIL, SUBJECT, MESSAGE_BODY, STATUS
                    ) VALUES (
                        :inquiry_id, :name, :email, :subject, :message, 'NEW'
                    )
                    """,
                    {
                        'inquiry_id': inquiry_id,
                        'name': name[:200],
                        'email': email[:200],
                        'subject': subject[:200] or 'General inquiry',
                        'message': message[:4000],
                    },
                )
            conn.commit()
        return True, 'Message sent successfully.'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
