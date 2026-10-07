"""MH_MEDIA queries for the ecommerce addon."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce.schema_bootstrap import ensure_media_schema
from db import _get_connection, _safe_rows, _table_exists

MEDIA_TABLE = 'MH_MEDIA'

PLACEMENTS = (
    'storefront_logo',
    'hero_bg',
    'hero',
    'promo',
    'showcase_banner',
    'category',
    'explore_category',
    'brand',
    'age_group',
    'product',
    'product_detail',
)


def media_table_ready() -> bool:
    try:
        ensure_media_schema()
    except Exception:
        return False
    return _table_exists(MEDIA_TABLE)


def _table_missing_message() -> str:
    return (
        'MH_MEDIA table is not installed in this database. '
        'Run MamaHub schema script sql/02_tables/16_mh_media.sql on the tenant DB.'
    )


def active_media_count() -> int:
    if not media_table_ready():
        return 0
    rows = _safe_rows(
        'SELECT COUNT(*) AS cnt FROM MH_MEDIA WHERE IS_ACTIVE = 1',
        {},
    )
    return int(rows[0]['cnt']) if rows else 0


def _parse_meta(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}


def _map_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **row,
        'meta': _parse_meta(row.get('meta_json')),
        'is_active': int(row.get('is_active') or 0) == 1,
    }


def list_media(
    *,
    placement: Optional[str] = None,
    active_only: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not media_table_ready():
        return [], _table_missing_message()

    where = ['1=1']
    params: Dict[str, Any] = {}
    if placement:
        where.append('PLACEMENT = :placement')
        params['placement'] = placement.strip()
    if active_only:
        where.append('IS_ACTIVE = 1')

    rows = _safe_rows(
        f"""
        SELECT
            MEDIA_ID AS media_id,
            PLACEMENT AS placement,
            REF_KEY AS ref_key,
            TITLE AS title,
            SUBTITLE AS subtitle,
            TITLE_AR AS title_ar,
            SUBTITLE_AR AS subtitle_ar,
            IMAGE_URL AS image_url,
            LINK_URL AS link_url,
            ALT_TEXT AS alt_text,
            SORT_ORDER AS sort_order,
            META_JSON AS meta_json,
            IS_ACTIVE AS is_active,
            CREATED_AT AS created_at
        FROM MH_MEDIA
        WHERE {' AND '.join(where)}
        ORDER BY PLACEMENT, SORT_ORDER, MEDIA_ID
        """,
        params,
    )
    return [_map_row(dict(row)) for row in rows], None


def get_media(media_id: int) -> Optional[Dict[str, Any]]:
    if not media_table_ready():
        return None
    rows = _safe_rows(
        """
        SELECT
            MEDIA_ID AS media_id,
            PLACEMENT AS placement,
            REF_KEY AS ref_key,
            TITLE AS title,
            SUBTITLE AS subtitle,
            TITLE_AR AS title_ar,
            SUBTITLE_AR AS subtitle_ar,
            IMAGE_URL AS image_url,
            LINK_URL AS link_url,
            ALT_TEXT AS alt_text,
            SORT_ORDER AS sort_order,
            META_JSON AS meta_json,
            IS_ACTIVE AS is_active,
            CREATED_AT AS created_at
        FROM MH_MEDIA
        WHERE MEDIA_ID = :media_id
        """,
        {'media_id': int(media_id)},
    )
    return _map_row(dict(rows[0])) if rows else None


def _clip_media_text(value: Any, max_chars: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_chars]


def _fit_meta_json(meta: Any, max_chars: int = 4000) -> str:
    """Keep META_JSON valid JSON inside the 4000-char column."""
    data = dict(meta) if isinstance(meta, dict) else {}
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw
    shrink_keys = sorted(
        (
            key
            for key, value in data.items()
            if key != 'compare_urls' and isinstance(value, str) and len(value) > 20
        ),
        key=lambda key: len(str(data.get(key) or '')),
        reverse=True,
    )
    while len(raw) > max_chars and shrink_keys:
        key = shrink_keys[0]
        value = str(data.get(key) or '')
        overflow = len(raw) - max_chars
        cut = max(20, len(value) - overflow - 20)
        if cut >= len(value):
            shrink_keys.pop(0)
            continue
        data[key] = value[:cut].rstrip()
        raw = json.dumps(data, ensure_ascii=False)
        if len(str(data.get(key) or '')) <= 20:
            shrink_keys.pop(0)
    return raw if len(raw) <= max_chars else json.dumps(
        {key: data[key] for key in data if key == 'compare_urls'},
        ensure_ascii=False,
    )[:max_chars]


def upsert_media(payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not media_table_ready():
        return False, _table_missing_message(), None

    media_id = payload.get('media_id')
    meta_json = _fit_meta_json(payload.get('meta') or {})
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if media_id:
                    cur.execute(
                        """
                        UPDATE MH_MEDIA SET
                            PLACEMENT = :placement,
                            REF_KEY = :ref_key,
                            TITLE = :title,
                            SUBTITLE = :subtitle,
                            TITLE_AR = :title_ar,
                            SUBTITLE_AR = :subtitle_ar,
                            IMAGE_URL = :image_url,
                            LINK_URL = :link_url,
                            ALT_TEXT = :alt_text,
                            SORT_ORDER = :sort_order,
                            META_JSON = :meta_json,
                            IS_ACTIVE = :is_active,
                            MODIFIED_AT = SYSTIMESTAMP
                        WHERE MEDIA_ID = :media_id
                        """,
                        {
                            'media_id': int(media_id),
                            'placement': payload['placement'],
                            'ref_key': payload.get('ref_key'),
                            'title': _clip_media_text(payload.get('title'), 200),
                            'subtitle': _clip_media_text(payload.get('subtitle'), 2000),
                            'title_ar': _clip_media_text(payload.get('title_ar'), 200),
                            'subtitle_ar': _clip_media_text(payload.get('subtitle_ar'), 2000),
                            'image_url': payload['image_url'],
                            'link_url': _clip_media_text(payload.get('link_url'), 500),
                            'alt_text': _clip_media_text(payload.get('alt_text'), 500),
                            'sort_order': int(payload.get('sort_order') or 0),
                            'meta_json': meta_json,
                            'is_active': 1 if payload.get('is_active', True) else 0,
                        },
                    )
                    saved_id = int(media_id)
                else:
                    cur.execute('SELECT SEQ_MH_MEDIA_ID.NEXTVAL AS id FROM DUAL')
                    saved_id = int((cur.fetchone() or [0])[0])
                    cur.execute(
                        """
                        INSERT INTO MH_MEDIA (
                            MEDIA_ID, PLACEMENT, REF_KEY, TITLE, SUBTITLE, TITLE_AR, SUBTITLE_AR, IMAGE_URL,
                            LINK_URL, ALT_TEXT, SORT_ORDER, META_JSON, IS_ACTIVE
                        ) VALUES (
                            :media_id, :placement, :ref_key, :title, :subtitle, :title_ar, :subtitle_ar, :image_url,
                            :link_url, :alt_text, :sort_order, :meta_json, :is_active
                        )
                        """,
                        {
                            'media_id': saved_id,
                            'placement': payload['placement'],
                            'ref_key': payload.get('ref_key'),
                            'title': _clip_media_text(payload.get('title'), 200),
                            'subtitle': _clip_media_text(payload.get('subtitle'), 2000),
                            'title_ar': _clip_media_text(payload.get('title_ar'), 200),
                            'subtitle_ar': _clip_media_text(payload.get('subtitle_ar'), 2000),
                            'image_url': payload['image_url'],
                            'link_url': _clip_media_text(payload.get('link_url'), 500),
                            'alt_text': _clip_media_text(payload.get('alt_text'), 500),
                            'sort_order': int(payload.get('sort_order') or 0),
                            'meta_json': meta_json,
                            'is_active': 1 if payload.get('is_active', True) else 0,
                        },
                    )
            conn.commit()
        saved = get_media(saved_id)
        return True, 'Media saved', saved
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def deactivate_media(media_id: int) -> Tuple[bool, str]:
    if not media_table_ready():
        return False, _table_missing_message()
    existing = get_media(media_id)
    if not existing:
        return False, 'Media not found'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_MEDIA
                    SET IS_ACTIVE = 0, MODIFIED_AT = SYSTIMESTAMP
                    WHERE MEDIA_ID = :media_id
                    """,
                    {'media_id': int(media_id)},
                )
            conn.commit()
        return True, 'Media deactivated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
