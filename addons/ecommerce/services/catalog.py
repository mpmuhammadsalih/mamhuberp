"""Catalog helpers — products and categories from ERP tables."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce import media_db
from db import (
    _build_items_list_where,
    _safe_rows,
    ensure_itemmaster_description_width,
    ensure_itemmaster_image_path_column,
    get_category_master_tree,
    get_item_by_code,
    get_items_kpis,
    get_items_list,
)

from addons.ecommerce.services.common import resolve_location_code
from addons.ecommerce.services import item_age_groups as item_age_groups_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc

# Oracle treats '' as NULL, so TRIM(col) <> '' never matches. Use LENGTH(TRIM(...)).
_HAS_IMAGE_SQL = 'im.IMAGE_PATH IS NOT NULL AND LENGTH(TRIM(im.IMAGE_PATH)) > 0'
_MISSING_IMAGE_SQL = (
    'im.IMAGE_PATH IS NULL OR LENGTH(TRIM(im.IMAGE_PATH)) = 0 '
    'OR LENGTH(TRIM(im.IMAGE_PATH)) IS NULL'
)


def _image_filter_conditions(image_filter: str | None) -> List[str] | None:
    value = (image_filter or 'all').strip().lower()
    if value in ('missing', 'none', 'no', 'without'):
        return [_MISSING_IMAGE_SQL]
    if value in ('has', 'with', 'ok'):
        return [_HAS_IMAGE_SQL]
    return None


def _product_specs_text_map() -> Dict[str, str]:
    meta_map = web_meta_svc.product_web_meta_map()
    return {
        ref: str(data.get('specifications') or '').strip()
        for ref, data in meta_map.items()
        if str(data.get('specifications') or '').strip()
    }


def list_products(
    *,
    page: int = 1,
    per_page: int = 50,
    search: str | None = None,
    order_by: str | None = None,
    order_direction: str | None = None,
    web_filter: str | None = None,
    image_filter: str | None = None,
) -> Tuple[List[Dict[str, Any]], int, int]:
    from addons.ecommerce.services import product_edit as product_edit_svc

    ensure_itemmaster_image_path_column()
    loc = resolve_location_code()
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 200))
    meta_map = web_meta_svc.product_web_meta_map()
    hidden_codes = web_meta_svc.hidden_item_codes(meta_map)
    featured_codes = web_meta_svc.featured_item_codes(meta_map, require_visible=False)
    web = (web_filter or 'all').strip().lower()
    item_codes = None
    exclude_codes = None
    if web == 'hidden':
        item_codes = hidden_codes
        if not item_codes:
            return [], 0, loc
    elif web == 'featured':
        item_codes = featured_codes
        if not item_codes:
            return [], 0, loc
    elif web in ('on', 'visible', 'shown'):
        exclude_codes = hidden_codes or None
    items, total = get_items_list(
        location_code=loc,
        search=(search or '').strip() or None,
        page=page,
        items_per_page=per_page,
        include_lookup_names=True,
        order_by=(order_by or '').strip() or None,
        order_direction=(order_direction or '').strip() or None,
        item_codes=item_codes,
        exclude_item_codes=exclude_codes,
        extra_conditions=_image_filter_conditions(image_filter),
    )
    prepared: List[Dict[str, Any]] = []
    specs_map = _product_specs_text_map()
    for row in list(items or []):
        item = dict(row)
        image_path = item.get('image_path') or item.get('IMAGE_PATH') or ''
        item['image_url'] = product_edit_svc.product_image_public_url(image_path)
        desc = item.get('description') or item.get('DESCRIPTION') or ''
        item['description_text'] = str(desc).strip() if desc is not None else ''
        code = item.get('itemcode') or item.get('ITEMCODE') or item.get('code')
        item['specifications_text'] = specs_map.get(str(code or '').strip(), '')
        wholesale = item.get('wholesaleprice') or item.get('WHOLESALEPRICE')
        meta_offer = web_meta_svc.resolve_offer_price(
            int(code or 0),
            wholesale_price=wholesale,
            meta_map=meta_map,
        )
        if meta_offer is not None:
            item['wholesaleprice'] = meta_offer
            item['WHOLESALEPRICE'] = meta_offer
        meta = meta_map.get(str(code or '').strip(), {})
        item['show_on_web'] = web_meta_svc.show_on_web_from_meta(meta)
        item['is_featured'] = web_meta_svc.is_featured_from_meta(meta)
        item['is_addon'] = web_meta_svc.is_addon_from_meta(meta)
        prepared.append(item)
    return prepared, int(total or 0), loc


def _gallery_admin_url(image_url: str | None) -> str | None:
    from addons.ecommerce.services import product_edit as product_edit_svc

    raw = str(image_url or '').strip()
    if not raw:
        return None
    if raw.startswith('/media/files/'):
        filename = raw.split('/media/files/')[-1].split('?')[0]
        try:
            from nexa_http import url_for

            return url_for('ecommerce.media_file', filename=filename)
        except Exception:
            return f'/ecommerce/media/files/{filename}'
    return product_edit_svc.product_image_public_url(raw)


def _product_gallery_rows(item_code: int) -> List[Dict[str, Any]]:
    if not media_db.media_table_ready():
        return []
    rows, _ = media_db.list_media(placement='product', active_only=True)
    gallery = [
        row for row in rows if str(row.get('ref_key') or '').strip() == str(item_code)
    ]
    gallery.sort(key=lambda row: (row.get('sort_order') or 0, row.get('media_id') or 0))
    out: List[Dict[str, Any]] = []
    for row in gallery:
        out.append(
            {
                'media_id': row.get('media_id'),
                'image_url': _gallery_admin_url(row.get('image_url')),
                'sort_order': row.get('sort_order') or 0,
            }
        )
    return out


def _offer_price_for_form(item: Dict[str, Any], item_code: int, meta_map: Dict[str, Dict[str, Any]]) -> str | float:
    """Return ecommerce offer for admin form — meta first, then ITEMMASTER wholesale."""
    offer = web_meta_svc.resolve_offer_price(
        item_code,
        wholesale_price=item.get('wholesaleprice') if item.get('wholesaleprice') is not None else item.get('WHOLESALEPRICE'),
        meta_map=meta_map,
    )
    return offer if offer is not None else ''


def adjacent_product_codes(
    item_code: int,
    *,
    search: str | None = None,
    web_filter: str | None = None,
    image_filter: str | None = None,
    descending: bool = False,
) -> Tuple[Optional[int], Optional[int]]:
    """Previous and next ITEMCODE at this location, following item-code order."""
    loc = resolve_location_code()
    ic = int(item_code)
    if ic <= 0:
        return (None, None)

    meta_map = web_meta_svc.product_web_meta_map()
    hidden_codes = web_meta_svc.hidden_item_codes(meta_map)
    featured_codes = web_meta_svc.featured_item_codes(meta_map, require_visible=False)
    web = (web_filter or 'all').strip().lower()
    include_codes = None
    exclude_codes = None
    if web == 'hidden':
        include_codes = hidden_codes
        if not include_codes:
            return (None, None)
    elif web == 'featured':
        include_codes = featured_codes
        if not include_codes:
            return (None, None)
    elif web in ('on', 'visible', 'shown'):
        exclude_codes = hidden_codes or None

    where_clause, params = _build_items_list_where(
        'im',
        location_code=loc,
        search=(search or '').strip() or None,
        item_codes=include_codes,
        exclude_item_codes=exclude_codes,
        extra_conditions=_image_filter_conditions(image_filter),
    )
    params['ic'] = ic
    extra = 'AND' if where_clause else 'WHERE'
    lower_rows = _safe_rows(
        f'SELECT MAX(im.ITEMCODE) AS item_code FROM ITEMMASTER im {where_clause} {extra} im.ITEMCODE < :ic',
        params,
    )
    higher_rows = _safe_rows(
        f'SELECT MIN(im.ITEMCODE) AS item_code FROM ITEMMASTER im {where_clause} {extra} im.ITEMCODE > :ic',
        params,
    )

    def _code(rows: List[Dict[str, Any]]) -> Optional[int]:
        if not rows:
            return None
        raw = rows[0].get('item_code') or rows[0].get('ITEMCODE')
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    lower = _code(lower_rows)
    higher = _code(higher_rows)
    if descending:
        return (higher, lower)
    return (lower, higher)


def get_product_for_edit(item_code: int) -> Dict[str, Any] | None:
    from addons.ecommerce.services import product_edit as product_edit_svc

    ensure_itemmaster_image_path_column()
    ensure_itemmaster_description_width()
    loc = resolve_location_code()
    row = get_item_by_code(int(item_code), loc)
    if not row:
        return None
    item = dict(row)
    image_path = item.get('image_path') or item.get('IMAGE_PATH') or ''
    desc = item.get('description') or item.get('DESCRIPTION') or ''
    specs_map = _product_specs_text_map()
    meta_map = web_meta_svc.product_web_meta_map()
    code = item.get('itemcode') or item.get('ITEMCODE') or item.get('code') or item_code
    meta = meta_map.get(str(code), {})
    age_groups = item_age_groups_svc.list_age_groups()
    age_group_ids = item_age_groups_svc.get_item_age_group_ids(int(code))
    all_age_ids = []
    for row in age_groups:
        try:
            all_age_ids.append(int(row.get('age_group_id')))
        except (TypeError, ValueError):
            continue
    return {
        'item_code': int(code),
        'item_name': item.get('itemname') or item.get('ITEMNAME') or item.get('name') or '',
        'description_text': str(desc).strip() if desc is not None else '',
        'description_ar_text': str(meta.get('description_ar') or '').strip(),
        'specifications_text': specs_map.get(str(code), ''),
        'specifications_ar_text': str(meta.get('specifications_ar') or '').strip(),
        'retail_price': item.get('retailprice') or item.get('RETAILPRICE') or 0,
        'offer_price': _offer_price_for_form(item, int(code), meta_map),
        'current_stock': item.get('currentstock') or item.get('CURRENTSTOCK') or 0,
        'brand_name': item.get('brandname') or item.get('BRANDNAME') or item.get('brand_name') or '',
        'category_name': item.get('categoryname') or item.get('CATEGORYNAME') or item.get('category_name') or '',
        'image_url': product_edit_svc.product_image_public_url(image_path),
        'gallery_images': _product_gallery_rows(int(code)),
        'location_code': loc,
        'age_groups': age_groups,
        'age_group_ids': age_group_ids,
        'age_all_selected': bool(all_age_ids) and set(all_age_ids).issubset(set(age_group_ids)),
        'seo_title': str(meta.get('seo_title') or '').strip(),
        'seo_description': str(meta.get('seo_description') or '').strip(),
        'seo_title_auto': web_meta_svc.auto_seo_title(
            str(item.get('itemname') or item.get('ITEMNAME') or item.get('name') or '')
        ),
        'seo_description_auto': web_meta_svc.auto_seo_description(
            item_name=str(item.get('itemname') or item.get('ITEMNAME') or item.get('name') or ''),
            description=str(desc).strip() if desc is not None else '',
            category_name=str(
                item.get('categoryname') or item.get('CATEGORYNAME') or item.get('category_name') or ''
            ),
            price=_offer_price_for_form(item, int(code), meta_map)
            or item.get('retailprice')
            or item.get('RETAILPRICE')
            or 0,
        ),
        'show_on_web': web_meta_svc.show_on_web_from_meta(meta),
        'is_featured': web_meta_svc.is_featured_from_meta(meta),
        'is_addon': web_meta_svc.is_addon_from_meta(meta),
        'import_page_url': str(meta.get('import_page_url') or '').strip(),
        'compare_urls': list(meta.get('compare_urls') or []),
        'barcode': str(
            item.get('manufacturerid')
            or item.get('MANUFACTURERID')
            or item.get('rawabicode')
            or item.get('RAWABICODE')
            or ''
        ).strip(),
    }


def get_category_tree() -> Tuple[List[Dict[str, Any]], int]:
    loc = resolve_location_code()
    tree = get_category_master_tree(location_code=loc) or []
    return tree, loc


def inventory_snapshot() -> Dict[str, Any]:
    loc = resolve_location_code()
    kpis = get_items_kpis(location_code=loc) or {}
    return {
        'location_code': loc,
        'total_products': int(kpis.get('total_items') or 0),
        'active_products': int(kpis.get('active_items') or 0),
        'low_stock': int(kpis.get('low_stock_items') or 0),
        'inventory_value': float(kpis.get('inventory_value') or 0),
    }


def list_inventory_items(
    *,
    page: int = 1,
    per_page: int = 50,
    search: str | None = None,
    stock_filter: str = 'issues',
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Paginated low/out-of-stock items for the inventory admin page."""
    loc = resolve_location_code()
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 50), 200))
    offset = (page - 1) * per_page

    where = [
        'im.LOCATIONCODE = :location_code',
        "NVL(im.ITEMFLAG, 'Y') <> 'N'",
    ]
    params: Dict[str, Any] = {
        'location_code': loc,
        'max_row': offset + per_page,
        'min_row': offset,
    }
    sf = (stock_filter or 'issues').strip().lower()
    if sf == 'out':
        where.append('NVL(im.CURRENTSTOCK, 0) <= 0')
    elif sf == 'low':
        where.append('NVL(im.CURRENTSTOCK, 0) > 0 AND NVL(im.CURRENTSTOCK, 0) <= 10')
    else:
        where.append('NVL(im.CURRENTSTOCK, 0) <= 10')
    if search:
        where.append(
            "(UPPER(im.ITEMNAME) LIKE :search OR TO_CHAR(im.ITEMCODE) LIKE :search "
            "OR UPPER(NVL(im.MANUFACTURERID, '')) LIKE :search)"
        )
        params['search'] = f'%{search.strip().upper()}%'

    where_sql = ' AND '.join(where)
    count_rows = _safe_rows(
        f'SELECT COUNT(*) AS cnt FROM ITEMMASTER im WHERE {where_sql}',
        params,
    )
    total = int(count_rows[0]['cnt']) if count_rows else 0
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT inner_q.*, ROWNUM rnum FROM (
                SELECT
                    im.ITEMCODE AS item_code,
                    im.ITEMNAME AS item_name,
                    NVL(im.CURRENTSTOCK, 0) AS current_stock,
                    NVL(im.RETAILPRICE, 0) AS retail_price,
                    im.CATEGORYCODE AS category_code,
                    im.BRANDCODE AS brand_code
                FROM ITEMMASTER im
                WHERE {where_sql}
                ORDER BY im.CURRENTSTOCK ASC, im.ITEMCODE
            ) inner_q
            WHERE ROWNUM <= :max_row
        )
        WHERE rnum > :min_row
        """,
        params,
    )
    return rows, total, loc
