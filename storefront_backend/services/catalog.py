"""Catalog mapping and queries for storefront API."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from addons.ecommerce import media_db
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from db import _safe_rows, _table_exists, get_category_master_tree, get_item_by_code, get_items_list

from storefront_backend.deps import resolve_location_code
from storefront_backend.services.item_images import public_item_image_url
from storefront_backend.services.schema_bootstrap import ensure_age_group_schema
from storefront_backend.utils.response import build_pagination_meta


def _resolve_age_slug(age_slug: Optional[str]) -> Optional[int]:
    if not age_slug or not _table_exists('MH_AGE_GROUP'):
        return None
    rows = _safe_rows(
        """
        SELECT AGE_GROUP_ID AS age_group_id
        FROM MH_AGE_GROUP
        WHERE LOWER(SLUG) = LOWER(:slug) AND IS_ACTIVE = 1
        """,
        {'slug': age_slug.strip()},
    )
    return int(rows[0]['age_group_id']) if rows else None


def _resolve_interest_slug(interest_slug: Optional[str]) -> Optional[int]:
    if not interest_slug or not _table_exists('MH_INTEREST'):
        return None
    rows = _safe_rows(
        """
        SELECT INTEREST_ID AS interest_id
        FROM MH_INTEREST
        WHERE LOWER(SLUG) = LOWER(:slug) AND IS_ACTIVE = 1
        """,
        {'slug': interest_slug.strip()},
    )
    return int(rows[0]['interest_id']) if rows else None


def _item_codes_for_age_group(age_group_id: int) -> List[int]:
    if not _table_exists('MH_ITEM_AGE_GROUP'):
        return []
    rows = _safe_rows(
        """
        SELECT DISTINCT ITEM_CODE AS item_code
        FROM MH_ITEM_AGE_GROUP
        WHERE AGE_GROUP_ID = :age_group_id
        """,
        {'age_group_id': int(age_group_id)},
    )
    return [int(r['item_code']) for r in rows]


def _item_codes_for_interest(interest_id: int) -> List[int]:
    if not _table_exists('MH_ITEM_INTEREST'):
        return []
    rows = _safe_rows(
        """
        SELECT DISTINCT ITEM_CODE AS item_code
        FROM MH_ITEM_INTEREST
        WHERE INTEREST_ID = :interest_id
        """,
        {'interest_id': int(interest_id)},
    )
    return [int(r['item_code']) for r in rows]


def _intersect_item_codes(*groups: Optional[List[int]]) -> Optional[List[int]]:
    sets: List[Set[int]] = [set(g) for g in groups if g is not None]
    if not sets:
        return None
    combined = sets[0]
    for group in sets[1:]:
        combined &= group
    return list(combined)


def _float_price(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def resolve_offer_price(retail: float, wholesale: float) -> Optional[float]:
    """Return sale price when wholesale is a valid offer below retail."""
    if wholesale > 0 and retail > 0 and wholesale < retail:
        return wholesale
    return None


def effective_unit_price(retail: float, wholesale: float) -> float:
    """Price charged at checkout — offer when valid, otherwise retail."""
    offer = resolve_offer_price(retail, wholesale)
    return offer if offer is not None else retail


def _attach_arabic_names(rows: List[Dict[str, Any]], location_code: int) -> None:
    """Attach ITEMNAMEARA to list rows via batch lookup."""
    if not rows:
        return
    try:
        from db import (
            _detect_column,
            _detect_table,
            _fetch_rows_itemnameara_only,
            _fix_mojibake,
            _get_table_columns,
        )
    except ImportError:
        return

    im_cols = {str(c).upper() for c in (_get_table_columns('ITEMMASTER') or [])}
    if 'ITEMNAMEARA' not in im_cols:
        return

    codes: List[str] = []
    seen: Set[str] = set()
    for row in rows:
        raw = row.get('itemcode') or row.get('ITEMCODE')
        if raw is None:
            continue
        code = str(raw).strip()
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return

    imx = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER']) or 'ITEMMASTER'
    ic_col = _detect_column(imx, ['ITEMCODE', 'ITEM_CODE', 'itemcode']) or 'ITEMCODE'
    lc_col = _detect_column(imx, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode']) or 'LOCATIONCODE'
    by_code: Dict[str, str] = {}
    nls_lang = (os.environ.get('NLS_LANG') or 'AMERICAN_AMERICA.UTF8').strip() or 'AMERICAN_AMERICA.UTF8'

    for start in range(0, len(codes), 900):
        chunk = codes[start : start + 900]
        chunk_params: Dict[str, Any] = {'loc': int(location_code)}
        bind_parts: List[str] = []
        for i, code in enumerate(chunk):
            key = f'c{i}'
            bind_parts.append(f':{key}')
            chunk_params[key] = code
        in_list = ', '.join(bind_parts)
        query = f"""
        SELECT TO_CHAR(im.{ic_col}) AS itemcode, im.ITEMNAMEARA AS itemnameara
        FROM {imx} im
        WHERE im.{lc_col} = :loc AND TO_CHAR(im.{ic_col}) IN ({in_list})
        """
        try:
            im_rows = _fetch_rows_itemnameara_only(None, query, chunk_params, nls_lang=nls_lang)
        except Exception:
            im_rows = []
        for r in im_rows or []:
            ic = str(r.get('itemcode') or '').strip()
            if not ic:
                continue
            ara_raw = _fix_mojibake(r.get('itemnameara'))
            by_code[ic] = str(ara_raw).strip() if ara_raw is not None else ''

    for row in rows:
        ic = str(row.get('itemcode') or row.get('ITEMCODE') or '').strip()
        if ic in by_code:
            row['itemnameara'] = by_code[ic]


_MH_BRAND_NAME_AR_READY = False


def _ensure_mh_brand_name_ar_column() -> bool:
    global _MH_BRAND_NAME_AR_READY
    if _MH_BRAND_NAME_AR_READY:
        return True
    if not _table_exists('MH_BRAND'):
        return False
    try:
        from db import _TABLE_COLUMNS_CACHE, _get_connection, _get_table_columns
    except ImportError:
        return False
    cols = {str(c).upper() for c in (_get_table_columns('MH_BRAND') or [])}
    if 'BRAND_NAME_AR' in cols:
        _MH_BRAND_NAME_AR_READY = True
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('ALTER TABLE MH_BRAND ADD (BRAND_NAME_AR VARCHAR2(200 CHAR))')
            conn.commit()
        _TABLE_COLUMNS_CACHE.pop('MH_BRAND', None)
        _MH_BRAND_NAME_AR_READY = True
        return True
    except Exception:
        cols = {str(c).upper() for c in (_get_table_columns('MH_BRAND') or [])}
        _MH_BRAND_NAME_AR_READY = 'BRAND_NAME_AR' in cols
        return _MH_BRAND_NAME_AR_READY


def _normalize_brand_name_ar(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    try:
        from db import _fix_mojibake
    except ImportError:
        _fix_mojibake = lambda v: v  # noqa: E731
    fixed = _fix_mojibake(raw)
    text = str(fixed).strip() if fixed is not None else ''
    return text or None


def _brand_name_ar_map(brand_codes: List[int], location_code: int) -> Dict[int, str]:
    if not brand_codes or not _table_exists('CATEGORY'):
        return {}
    try:
        from db import ensure_category_nameara_column, _get_table_columns
    except ImportError:
        return {}
    if not ensure_category_nameara_column():
        return {}
    cols = {str(c).upper() for c in (_get_table_columns('CATEGORY') or [])}
    if 'NAMEARA' not in cols:
        return {}
    mapping: Dict[int, str] = {}
    unique_codes = sorted({int(c) for c in brand_codes if c is not None})
    for start in range(0, len(unique_codes), 900):
        chunk = unique_codes[start : start + 900]
        params: Dict[str, Any] = {'loc': int(location_code)}
        bind_parts: List[str] = []
        for i, code in enumerate(chunk):
            key = f'b{i}'
            bind_parts.append(f':{key}')
            params[key] = code
        in_list = ', '.join(bind_parts)
        rows = _safe_rows(
            f"""
            SELECT CODE AS brand_code, NAMEARA AS nameara
            FROM CATEGORY
            WHERE LOCATIONCODE = :loc
              AND UPPER(TRIM(TO_CHAR(FLAG))) = 'B'
              AND CODE IN ({in_list})
            """,
            params,
        )
        for row in rows or []:
            try:
                code = int(row.get('brand_code') or 0)
            except (TypeError, ValueError):
                continue
            ara = _normalize_brand_name_ar(row.get('nameara'))
            if code and ara:
                mapping[code] = ara
    return mapping


def _attach_brand_name_ar(rows: List[Dict[str, Any]], location_code: int) -> None:
    if not rows:
        return
    codes: List[int] = []
    seen: Set[int] = set()
    for row in rows:
        raw = row.get('brandcode') or row.get('BRANDCODE') or row.get('brand_code')
        if raw is None:
            continue
        try:
            code = int(raw)
        except (TypeError, ValueError):
            continue
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return
    by_code = _brand_name_ar_map(codes, location_code)
    for row in rows:
        raw = row.get('brandcode') or row.get('BRANDCODE') or row.get('brand_code')
        try:
            code = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            continue
        if code in by_code:
            row['brandnameara'] = by_code[code]


def _item_name_fields(row: Dict[str, Any]) -> tuple[str, Optional[str]]:
    try:
        from db import _fix_mojibake
    except ImportError:
        _fix_mojibake = lambda v: v  # noqa: E731

    en_name = str(row.get('itemname') or row.get('ITEMNAME') or '').strip()
    ara_raw = row.get('itemnameara') or row.get('ITEMNAMEARA')
    ara_name = ''
    if ara_raw is not None:
        fixed = _fix_mojibake(ara_raw)
        ara_name = str(fixed).strip() if fixed is not None else ''
    return en_name, ara_name or None


def _map_item_row(
    row: Dict[str, Any],
    *,
    meta_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    retail = _float_price(row.get('retailprice') or row.get('RETAILPRICE') or row.get('retail_price'))
    wholesale = _float_price(
        row.get('wholesaleprice') or row.get('WHOLESALEPRICE') or row.get('wholesale_price')
    )
    item_code = row.get('itemcode') or row.get('ITEMCODE')
    if item_code is not None:
        resolved = web_meta_svc.resolve_offer_price(
            int(item_code),
            wholesale_price=wholesale,
            meta_map=meta_map,
        )
        if resolved is not None:
            wholesale = resolved
    offer_price = resolve_offer_price(retail, wholesale)
    discount_percent: Optional[int] = None
    if offer_price is not None:
        discount_percent = int(round((retail - offer_price) / retail * 100))

    image_path = row.get('image_path') or row.get('IMAGE_PATH') or None
    image_url = public_item_image_url(image_path)
    en_name, ara_name = _item_name_fields(row)
    brand_ara = _normalize_brand_name_ar(row.get('brandnameara') or row.get('BRANDNAMEARA'))

    return {
        'location_code': row.get('locationcode') or row.get('LOCATIONCODE'),
        'item_code': row.get('itemcode') or row.get('ITEMCODE'),
        'item_name': en_name,
        'item_name_ar': ara_name,
        'retail_price': retail,
        'wholesale_price': wholesale,
        'offer_price': offer_price,
        'discount_percent': discount_percent,
        'current_stock': float(row.get('currentstock') or row.get('CURRENTSTOCK') or 0),
        'brand_code': row.get('brandcode') or row.get('BRANDCODE'),
        'category_code': row.get('categorycode') or row.get('CATEGORYCODE'),
        'category_name': row.get('categoryname') or row.get('CATEGORYNAME') or '',
        'brand_name': row.get('brandname') or row.get('BRANDNAME') or '',
        'brand_name_ar': brand_ara,
        'image_url': image_url,
        'primary_image_url': image_url,
    }


def list_products(
    *,
    location_code: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    category_code: Optional[int] = None,
    brand_code: Optional[int] = None,
    stock_filter: Optional[str] = None,
    age_slug: Optional[str] = None,
    interest_slug: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    item_codes: Optional[List[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    loc = resolve_location_code(location_code)
    requested_in_stock = (stock_filter or '').strip().lower() == 'in_stock'
    sf = stock_filter if stock_filter not in (None, 'all') else None
    if sf == 'in_stock':
        sf = 'greater'

    age_id = _resolve_age_slug(age_slug)
    interest_id = _resolve_interest_slug(interest_slug)
    filtered_codes = _intersect_item_codes(
        item_codes,
        _item_codes_for_age_group(age_id) if age_id is not None else None,
        _item_codes_for_interest(interest_id) if interest_id is not None else None,
    )
    if age_id is not None or interest_id is not None or item_codes is not None:
        if filtered_codes is not None and not filtered_codes:
            meta = build_pagination_meta(page=page, page_size=page_size, total_records=0)
            return [], meta

    rows, total = get_items_list(
        location_code=loc,
        search=(search or '').strip() or None,
        page=max(1, page),
        items_per_page=max(1, min(page_size, 200)),
        category_code=category_code,
        brand_code=brand_code,
        stock_filter=sf,
        item_codes=filtered_codes,
        order_by=sort,
        order_direction=order,
        include_lookup_names=True,
    )
    if requested_in_stock and int(total or 0) == 0:
        rows, total = get_items_list(
            location_code=loc,
            search=(search or '').strip() or None,
            page=max(1, page),
            items_per_page=max(1, min(page_size, 200)),
            category_code=category_code,
            brand_code=brand_code,
            stock_filter=None,
            item_codes=filtered_codes,
            order_by=sort,
            order_direction=order,
            include_lookup_names=True,
        )
    row_dicts = [dict(r) for r in rows]
    _attach_arabic_names(row_dicts, loc)
    _attach_brand_name_ar(row_dicts, loc)
    items = [_map_item_row(r, meta_map=web_meta_svc.product_web_meta_map()) for r in row_dicts]
    if min_price is not None:
        items = [i for i in items if float(i.get('retail_price') or 0) >= float(min_price)]
    if max_price is not None:
        items = [i for i in items if float(i.get('retail_price') or 0) <= float(max_price)]
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=int(total or 0))
    return items, meta


def get_product(item_code: int, *, location_code: Optional[int] = None) -> Optional[Dict[str, Any]]:
    loc = resolve_location_code(location_code)
    row = get_item_by_code(int(item_code), loc)
    if not row:
        return None
    row_dict = dict(row)
    _attach_brand_name_ar([row_dict], loc)
    meta_map = web_meta_svc.product_web_meta_map()
    mapped = _map_item_row(row_dict, meta_map=meta_map)
    mapped['description'] = str(row.get('description') or row.get('DESCRIPTION') or '').strip()
    meta = meta_map.get(str(item_code), {})
    mapped['description_ar'] = str(meta.get('description_ar') or '').strip() or None
    mapped['base_uom'] = row.get('baseuom') or row.get('BASEUOM') or ''
    mapped['packing'] = str(row.get('packing') or row.get('PACKING') or '').strip()
    mapped['manufacturer_id'] = str(row.get('manufacturerid') or row.get('MANUFACTURERID') or '').strip()
    mapped['images'] = _product_gallery_images(int(item_code), mapped.get('primary_image_url'))
    mapped['specifications'] = _product_specifications(row, int(item_code))
    specs_ar = _product_specifications_ar(int(item_code))
    mapped['specifications_ar'] = specs_ar if specs_ar else None
    return mapped


def _product_gallery_images(item_code: int, primary_url: str | None) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(url: str | None, *, primary: bool = False, image_id: int | None = None) -> None:
        if not url:
            return
        value = str(url).strip()
        if value.startswith('/api/'):
            resolved = value
        elif value.startswith('/media/files/') or value.startswith('uploads/'):
            resolved = _public_media_url(value) or public_item_image_url(value)
        else:
            resolved = public_item_image_url(value) or _public_media_url(value)
        if not resolved or resolved in seen:
            return
        seen.add(resolved)
        images.append({'id': image_id, 'image_url': resolved, 'primary': primary})

    add(primary_url, primary=True)

    if media_db.media_table_ready():
        rows, _ = media_db.list_media(placement='product', active_only=True)
        gallery_rows = [
            row
            for row in rows
            if str(row.get('ref_key') or '').strip() == str(item_code)
        ]
        gallery_rows.sort(key=lambda row: (row.get('sort_order') or 0, row.get('media_id') or 0))
        for row in gallery_rows:
            add(row.get('image_url'), image_id=row.get('media_id'))

    return images


def _parse_custom_specifications_text(custom: Any) -> List[Dict[str, str]]:
    specs: List[Dict[str, str]] = []

    def add(label: str, value: Any) -> None:
        text = str(value or '').strip()
        if text:
            specs.append({'label': label, 'value': text})

    if isinstance(custom, list):
        for entry in custom:
            if isinstance(entry, dict):
                add(str(entry.get('label') or ''), entry.get('value'))
        return specs

    if isinstance(custom, str) and custom.strip():
        feature_lines: List[str] = []
        for line in custom.strip().splitlines():
            text = line.strip()
            if not text:
                continue
            if ':' in text and not text.startswith('http'):
                label, value = text.split(':', 1)
                add(label.strip(), value.strip())
            else:
                feature_lines.append(text)
        for feature in feature_lines:
            add('Details', feature)
    return specs


def _product_specifications(row: Dict[str, Any], item_code: int) -> List[Dict[str, str]]:
    specs: List[Dict[str, str]] = []

    def add(label: str, value: Any) -> None:
        text = str(value or '').strip()
        if text:
            specs.append({'label': label, 'value': text})

    add('Item code', item_code)
    add('Brand', row.get('brandname') or row.get('BRANDNAME'))
    add('Category', row.get('categoryname') or row.get('CATEGORYNAME'))
    stock = row.get('currentstock') or row.get('CURRENTSTOCK')
    if stock is not None:
        add('Availability', f'{int(float(stock))} in stock' if float(stock) > 0 else 'Out of stock')
    add('Unit', row.get('baseuom') or row.get('BASEUOM'))
    add('Packing', row.get('packing') or row.get('PACKING'))
    add('Manufacturer ID', row.get('manufacturerid') or row.get('MANUFACTURERID'))
    vat = row.get('vatpercent') or row.get('VATPERCENT')
    if vat is not None and str(vat).strip() != '':
        add('VAT', f'{vat}%')

    if media_db.media_table_ready():
        rows, _ = media_db.list_media(placement='product_detail', active_only=True)
        detail = next((r for r in rows if str(r.get('ref_key') or '').strip() == str(item_code)), None)
        if detail:
            meta = detail.get('meta') or {}
            custom = meta.get('specifications')
            specs.extend(_parse_custom_specifications_text(custom))
            extra = str(detail.get('subtitle') or '').strip()
            if extra and not (isinstance(custom, str) and custom.strip()):
                specs.extend(_parse_custom_specifications_text(extra))

    return specs


def _product_specifications_ar(item_code: int) -> List[Dict[str, str]]:
    if not media_db.media_table_ready():
        return []
    rows, _ = media_db.list_media(placement='product_detail', active_only=True)
    detail = next((r for r in rows if str(r.get('ref_key') or '').strip() == str(item_code)), None)
    if not detail:
        return []
    meta = detail.get('meta') or {}
    custom_ar = meta.get('specifications_ar')
    if not custom_ar:
        return []
    return _parse_custom_specifications_text(custom_ar)


def _category_image_map() -> Dict[str, str]:
    if not media_db.media_table_ready():
        return {}
    rows, _ = media_db.list_media(placement='category', active_only=True)
    mapping: Dict[str, str] = {}
    for row in rows:
        ref = row.get('ref_key')
        url = _public_media_url(row.get('image_url'))
        if ref and url:
            mapping[str(ref).strip()] = url
    return mapping


def _attach_category_images(nodes: List[Dict[str, Any]], images: Dict[str, str]) -> None:
    for node in nodes:
        code = node.get('code')
        if code is not None:
            node['image_url'] = images.get(str(code))
        children = node.get('children')
        if isinstance(children, list) and children:
            _attach_category_images(children, images)


def get_category_tree(*, location_code: Optional[int] = None) -> List[Dict[str, Any]]:
    loc = resolve_location_code(location_code)
    tree = get_category_master_tree(location_code=loc) or []
    _attach_category_images(tree, _category_image_map())
    return tree


def list_brands() -> List[Dict[str, Any]]:
    loc = resolve_location_code(None)
    _ensure_mh_brand_name_ar_column()
    try:
        from db import ensure_category_nameara_column, _get_table_columns
    except ImportError:
        ensure_category_nameara_column = lambda: False  # type: ignore[misc, assignment]
        _get_table_columns = lambda _t: []  # type: ignore[misc, assignment]

    if _table_exists('MH_BRAND'):
        mh_cols = {str(c).upper() for c in (_get_table_columns('MH_BRAND') or [])}
        name_ar_sel = (
            'BRAND_NAME_AR AS brand_name_ar'
            if 'BRAND_NAME_AR' in mh_cols
            else 'CAST(NULL AS VARCHAR2(200 CHAR)) AS brand_name_ar'
        )
        rows = _safe_rows(
            f"""
            SELECT
                BRAND_ID AS brand_id,
                BRAND_CODE AS brand_code,
                BRAND_NAME AS brand_name,
                {name_ar_sel},
                SLUG AS slug,
                LOGO_URL AS logo_url,
                ERP_BRAND_CODE AS erp_brand_code,
                IS_FEATURED AS is_featured
            FROM MH_BRAND
            WHERE IS_ACTIVE = 1
            ORDER BY SORT_ORDER, BRAND_NAME
            """,
            {},
        )
        missing_erp: List[int] = []
        for row in rows:
            row['name_ar'] = _normalize_brand_name_ar(row.get('brand_name_ar'))
            if not row.get('name_ar'):
                erp = row.get('erp_brand_code')
                try:
                    if erp is not None:
                        missing_erp.append(int(erp))
                except (TypeError, ValueError):
                    pass
        erp_map = _brand_name_ar_map(missing_erp, loc) if missing_erp else {}
        for row in rows:
            if row.get('name_ar'):
                continue
            erp = row.get('erp_brand_code')
            try:
                erp_code = int(erp) if erp is not None else 0
            except (TypeError, ValueError):
                erp_code = 0
            if erp_code and erp_code in erp_map:
                row['name_ar'] = erp_map[erp_code]
        return rows

    ensure_category_nameara_column()
    cat_cols = {str(c).upper() for c in (_get_table_columns('CATEGORY') or [])}
    name_ar_sel = (
        'NAMEARA AS name_ar'
        if 'NAMEARA' in cat_cols
        else 'CAST(NULL AS VARCHAR2(100)) AS name_ar'
    )
    return _safe_rows(
        f"""
        SELECT CODE AS brand_code, NAME AS brand_name, {name_ar_sel}
        FROM CATEGORY
        WHERE UPPER(TRIM(TO_CHAR(FLAG))) = 'B'
          AND LOCATIONCODE = :loc
        ORDER BY NAME
        """,
        {'loc': int(loc)},
    )


def _public_media_url(image_url: str | None) -> str | None:
    if not image_url:
        return None
    preview = media_svc.preview_filename(image_url)
    if preview:
        return f'/api/v1/media/files/{preview}'
    value = str(image_url).strip()
    if value.startswith(('http://', 'https://', '/api/')):
        return value
    return value or None


def _age_group_image_map() -> Dict[str, str]:
    if not media_db.media_table_ready():
        return {}
    rows, _ = media_db.list_media(placement='age_group', active_only=True)
    mapping: Dict[str, str] = {}
    for row in rows:
        ref = row.get('ref_key')
        url = _public_media_url(row.get('image_url'))
        if ref and url:
            mapping[str(ref)] = url
    return mapping


def list_age_groups() -> List[Dict[str, Any]]:
    ensure_age_group_schema()
    if not _table_exists('MH_AGE_GROUP'):
        return []
    images = _age_group_image_map()
    rows = _safe_rows(
        """
        SELECT
            AGE_GROUP_ID AS age_group_id,
            AGE_GROUP_CODE AS age_group_code,
            AGE_GROUP_NAME AS age_group_name,
            SLUG AS slug,
            MIN_AGE_MONTHS AS min_age_months,
            MAX_AGE_MONTHS AS max_age_months
        FROM MH_AGE_GROUP
        WHERE IS_ACTIVE = 1
        ORDER BY SORT_ORDER, AGE_GROUP_NAME
        """,
        {},
    )
    for row in rows:
        slug = str(row.get('slug') or '')
        row['image_url'] = images.get(slug)
    return rows


def list_interests() -> List[Dict[str, Any]]:
    if not _table_exists('MH_INTEREST'):
        return []
    return _safe_rows(
        """
        SELECT
            INTEREST_ID AS interest_id,
            INTEREST_CODE AS interest_code,
            INTEREST_NAME AS interest_name,
            SLUG AS slug
        FROM MH_INTEREST
        WHERE IS_ACTIVE = 1
        ORDER BY SORT_ORDER, INTEREST_NAME
        """,
        {},
    )


COLLECTION_META: Dict[str, Dict[str, str]] = {
    'new-arrivals': {
        'title': 'New arrivals',
        'description': 'Fresh toys just added to our shelves.',
    },
    'best-sellers': {
        'title': 'Best sellers',
        'description': 'Customer favourites flying off the shelves.',
    },
    'offers': {
        'title': 'Offers & deals',
        'description': 'Special prices on selected toys.',
    },
}


_BEST_SELLER_CACHE: tuple[float, List[int]] | None = None
_BEST_SELLER_CACHE_TTL_SEC = 900


def _offer_item_codes(location_code: int) -> List[int]:
    """Item codes with a valid sale price (meta or WHOLESALEPRICE), any stock level."""
    loc = int(location_code)
    meta_map = web_meta_svc.product_web_meta_map()
    rows = _safe_rows(
        """
        SELECT
            im.ITEMCODE AS item_code,
            NVL(im.RETAILPRICE, 0) AS retailprice,
            NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice
        FROM ITEMMASTER im
        WHERE im.LOCATIONCODE = :loc
        """,
        {'loc': loc},
    )
    codes: List[int] = []
    for row in rows:
        item_code = int(row.get('item_code') or 0)
        if item_code <= 0:
            continue
        retail = _float_price(row.get('retailprice'))
        wholesale = _float_price(row.get('wholesaleprice'))
        resolved_wholesale = web_meta_svc.resolve_offer_price(
            item_code,
            wholesale_price=wholesale,
            meta_map=meta_map,
        )
        if resolved_wholesale is None:
            continue
        if resolve_offer_price(retail, resolved_wholesale) is not None:
            codes.append(item_code)
    codes.sort(reverse=True)
    return codes


def _best_seller_item_codes(limit: int = 200) -> List[int]:
    global _BEST_SELLER_CACHE
    now = time.time()
    if _BEST_SELLER_CACHE and now - _BEST_SELLER_CACHE[0] < _BEST_SELLER_CACHE_TTL_SEC:
        return _BEST_SELLER_CACHE[1][: max(1, limit)]

    if not _table_exists('MH_ORDER_ITEM'):
        return []
    rows = _safe_rows(
        """
        SELECT item_code FROM (
            SELECT oi.ITEM_CODE AS item_code, SUM(NVL(oi.QUANTITY, 0)) AS units_sold
            FROM MH_ORDER_ITEM oi
            GROUP BY oi.ITEM_CODE
            ORDER BY units_sold DESC
        ) WHERE ROWNUM <= :limit
        """,
        {'limit': max(1, min(limit, 500))},
    )
    codes = [int(r['item_code']) for r in rows if r.get('item_code') is not None]
    _BEST_SELLER_CACHE = (now, codes)
    return codes[: max(1, limit)]


def get_collection(
    collection: str,
    *,
    location_code: Optional[int] = None,
    page: int = 1,
    page_size: int = 24,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    slug = (collection or '').strip().lower()
    info = COLLECTION_META.get(slug)
    if not info:
        raise ValueError(f'Unknown collection: {collection}')

    if slug == 'new-arrivals':
        products, meta = list_products(
            location_code=location_code,
            page=page,
            page_size=page_size,
            stock_filter='in_stock',
            sort='itemcode',
            order='DESC',
        )
    elif slug == 'best-sellers':
        codes = _best_seller_item_codes(limit=500)
        if codes:
            products, meta = list_products(
                location_code=location_code,
                page=page,
                page_size=page_size,
                stock_filter='in_stock',
                item_codes=codes,
            )
            order_map = {code: idx for idx, code in enumerate(codes)}
            products.sort(key=lambda p: order_map.get(int(p.get('item_code') or 0), 999999))
        else:
            products, meta = list_products(
                location_code=location_code,
                page=page,
                page_size=page_size,
                stock_filter='in_stock',
                sort='currentstock',
                order='DESC',
            )
    else:
        loc = resolve_location_code(location_code)
        offer_codes = _offer_item_codes(loc)
        total = len(offer_codes)
        page_num = max(1, page)
        page_limit = max(1, min(page_size, 200))
        offset = (page_num - 1) * page_limit
        page_codes = offer_codes[offset : offset + page_limit]
        if not page_codes:
            products = []
        else:
            rows, _ = get_items_list(
                location_code=loc,
                item_codes=page_codes,
                items_per_page=len(page_codes),
                include_lookup_names=True,
            )
            row_dicts = [dict(r) for r in rows]
            _attach_arabic_names(row_dicts, loc)
            _attach_brand_name_ar(row_dicts, loc)
            order_map = {code: idx for idx, code in enumerate(page_codes)}
            meta_map = web_meta_svc.product_web_meta_map()
            products = [_map_item_row(r, meta_map=meta_map) for r in row_dicts]
            products = [p for p in products if p.get('offer_price') is not None]
            products.sort(
                key=lambda p: (
                    order_map.get(int(p.get('item_code') or 0), 999999),
                )
            )
        meta = build_pagination_meta(page=page_num, page_size=page_limit, total_records=total)

    payload = {
        'collection': slug,
        'info': info,
        'products': products,
    }
    return payload, meta
