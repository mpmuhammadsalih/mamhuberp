"""Admin REST API — wraps ecommerce addon services and ERP queries."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from addons.ecommerce import customers_db
from addons.ecommerce import media_db
from addons.ecommerce import orders_db
from addons.ecommerce import promotions_db
from addons.ecommerce import reviews_db
from addons.ecommerce.services import catalog as erp_catalog_svc
from addons.ecommerce.services import media as media_svc
from db import (
    _get_connection,
    _safe_rows,
    _table_exists,
    insert_category_dept,
    insert_category_main,
    insert_category_micro,
    update_category_master_name,
)

from storefront_backend.deps import resolve_location_code
from storefront_backend.services import catalog as catalog_svc
from storefront_backend.utils.response import build_pagination_meta


def get_dashboard() -> Dict[str, Any]:
    loc = resolve_location_code()
    sales = _sales_summary(loc)
    recent = _recent_orders(8)
    products = _safe_rows(
        """
        SELECT COUNT(*) AS total_products
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :loc AND NVL(ITEMFLAG, 'Y') <> 'N'
        """,
        {'loc': loc},
    )
    return {
        **sales,
        'total_customers': customers_db.customer_count(),
        'active_promotions': promotions_db.active_promotion_count(),
        'total_products': int(products[0]['total_products']) if products else 0,
        'recent_orders': recent,
    }


def _sales_summary(location_code: int) -> Dict[str, Any]:
    if not orders_db.orders_tables_ready():
        return {
            'total_orders': 0,
            'total_revenue': 0.0,
            'confirmed_orders': 0,
            'cancelled_orders': 0,
        }
    rows = _safe_rows(
        """
        SELECT
            COUNT(*) AS total_orders,
            NVL(SUM(CASE WHEN ORDER_STATUS <> 'CANCELLED' THEN GRAND_TOTAL ELSE 0 END), 0) AS total_revenue,
            SUM(CASE WHEN ORDER_STATUS = 'CONFIRMED' THEN 1 ELSE 0 END) AS confirmed_orders,
            SUM(CASE WHEN ORDER_STATUS = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
        FROM MH_ORDER
        WHERE LOCATION_CODE = :location_code
        """,
        {'location_code': int(location_code)},
    )
    row = rows[0] if rows else {}
    return {
        'total_orders': int(row.get('total_orders') or 0),
        'total_revenue': float(row.get('total_revenue') or 0),
        'confirmed_orders': int(row.get('confirmed_orders') or 0),
        'cancelled_orders': int(row.get('cancelled_orders') or 0),
    }


def _recent_orders(limit: int = 10) -> List[Dict[str, Any]]:
    if not orders_db.orders_tables_ready():
        return []
    return _safe_rows(
        """
        SELECT
            o.ORDER_ID AS order_id,
            o.ORDER_NUMBER AS order_number,
            o.ORDER_STATUS AS order_status,
            o.GRAND_TOTAL AS grand_total,
            o.CURRENCY_CODE AS currency_code,
            o.CREATED_AT AS created_at,
            u.EMAIL AS customer_email
        FROM MH_ORDER o
        LEFT JOIN APP_USER u ON u.USER_ID = o.USER_ID
        ORDER BY o.ORDER_ID DESC
        FETCH FIRST :limit ROWS ONLY
        """,
        {'limit': int(limit)},
    )


def list_orders(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, total, _ = orders_db.list_orders(page=page, page_size=page_size, status=status)
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return rows, meta


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    return orders_db.get_order(order_id)


def update_order_status(
    order_id: int,
    status: str,
    *,
    notes: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    ok, message = orders_db.update_order_status(
        order_id, status, notes=notes, updated_by=updated_by
    )
    if not ok:
        return False, message, None
    return True, message, orders_db.get_order(order_id)


def list_products(
    *,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    items, total, _loc = erp_catalog_svc.list_products(
        page=page, per_page=page_size, search=search
    )
    from addons.ecommerce.services import product_web_meta as web_meta_svc

    meta_map = web_meta_svc.product_web_meta_map()
    mapped = [catalog_svc._map_item_row(dict(item), meta_map=meta_map) for item in items]
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return mapped, meta


def get_product(item_code: int) -> Optional[Dict[str, Any]]:
    return catalog_svc.get_product(item_code)


def list_promotions() -> List[Dict[str, Any]]:
    rows, _warning = promotions_db.list_promotions()
    return rows


def _parse_iso_datetime(value: Any) -> datetime:
    text = str(value or '').strip()
    if not text:
        raise ValueError('Date is required')
    text = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(text[:19] if 'T' in fmt or ' ' in fmt else text[:10], fmt)
            except ValueError:
                continue
    raise ValueError(f'Invalid date: {value}')


def create_promotion(payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    data = {
        'promotion_code': payload['promotion_code'],
        'promotion_name': payload['promotion_name'],
        'coupon_code': payload['coupon_code'],
        'promotion_type': payload['promotion_type'],
        'discount_value': float(payload['discount_value']),
        'min_order_amount': float(payload.get('min_order_amount') or 0),
        'max_discount_amount': payload.get('max_discount_amount'),
        'start_date': _parse_iso_datetime(payload['start_date']),
        'end_date': _parse_iso_datetime(payload['end_date']),
        'usage_limit': payload.get('usage_limit'),
        'usage_per_customer': int(payload.get('usage_per_customer') or 1),
    }
    if data['end_date'] <= data['start_date']:
        return False, 'End date must be after start date', None
    if data['promotion_type'] == 'PERCENTAGE' and data['discount_value'] > 100:
        return False, 'Percentage discount cannot exceed 100', None
    return promotions_db.create_promotion_with_coupon(data)


def update_promotion(promotion_id: int, payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    existing = promotions_db.get_promotion(promotion_id)
    if not existing:
        return False, 'Promotion not found', None
    data: Dict[str, Any] = {}
    for key in (
        'promotion_name', 'discount_value', 'min_order_amount',
        'max_discount_amount', 'usage_limit', 'is_active', 'coupon_is_active',
    ):
        if key in payload:
            data[key] = payload[key]
    if 'end_date' in payload and payload['end_date']:
        data['end_date'] = _parse_iso_datetime(payload['end_date'])
    ok, message = promotions_db.update_promotion(
        promotion_id,
        coupon_id=int(existing['coupon_id']),
        data=data,
    )
    if not ok:
        return False, message, None
    return True, message, promotions_db.get_promotion(promotion_id)


def list_customers(*, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, total = customers_db.list_customers(page=page, page_size=page_size)
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return rows, meta


def list_inventory(
    *,
    page: int = 1,
    page_size: int = 20,
    low_stock_only: bool = False,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    loc = resolve_location_code()
    offset = (page - 1) * page_size
    where = ["im.LOCATIONCODE = :location_code", "NVL(im.ITEMFLAG, 'Y') <> 'N'"]
    params: Dict[str, Any] = {
        'location_code': loc,
        'max_row': offset + page_size,
        'min_row': offset,
    }
    if low_stock_only:
        where.append('NVL(im.CURRENTSTOCK, 0) <= 5')
    if search:
        where.append("(UPPER(im.ITEMNAME) LIKE :search OR TO_CHAR(im.ITEMCODE) LIKE :search)")
        params['search'] = f'%{search.strip().upper()}%'
    where_sql = ' AND '.join(where)
    count = _safe_rows(f'SELECT COUNT(*) AS cnt FROM ITEMMASTER im WHERE {where_sql}', params)
    total = int(count[0]['cnt']) if count else 0
    rows = _safe_rows(
        f"""
        SELECT * FROM (
            SELECT a.*, ROWNUM rnum FROM (
                SELECT im.ITEMCODE AS item_code, im.ITEMNAME AS item_name,
                       NVL(im.CURRENTSTOCK, 0) AS current_stock,
                       NVL(im.RETAILPRICE, 0) AS retail_price,
                       im.BRANDCODE AS brand_code
                FROM ITEMMASTER im
                WHERE {where_sql}
                ORDER BY im.CURRENTSTOCK ASC, im.ITEMCODE
            ) a WHERE ROWNUM <= :max_row
        ) WHERE rnum > :min_row
        """,
        params,
    )
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return rows, meta


def list_staff_users(*, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    offset = (page - 1) * page_size
    count = _safe_rows(
        """
        SELECT COUNT(*) AS cnt FROM APP_USER
        WHERE USER_TYPE <> 'CUSTOMER' AND IS_ACTIVE = 1
        """,
        {},
    )
    total = int(count[0]['cnt']) if count else 0
    rows = _safe_rows(
        """
        SELECT * FROM (
            SELECT a.*, ROWNUM rnum FROM (
                SELECT
                    USER_ID AS user_id,
                    EMAIL AS email,
                    FIRST_NAME AS first_name,
                    LAST_NAME AS last_name,
                    USER_TYPE AS user_type,
                    ACCOUNT_STATUS AS account_status
                FROM APP_USER
                WHERE USER_TYPE <> 'CUSTOMER' AND IS_ACTIVE = 1
                ORDER BY USER_ID DESC
            ) a WHERE ROWNUM <= :max_row
        ) WHERE rnum > :min_row
        """,
        {'max_row': offset + page_size, 'min_row': offset},
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = int(row['user_id'])
        role_rows = _safe_rows(
            """
            SELECT r.ROLE_CODE AS role_code
            FROM USER_ROLE ur
            JOIN ROLE r ON r.ROLE_ID = ur.ROLE_ID
            WHERE ur.USER_ID = :user_id
            """,
            {'user_id': uid},
        ) if _table_exists('USER_ROLE') else []
        out.append({**row, 'roles': [r['role_code'] for r in role_rows]})
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return out, meta


def list_roles() -> List[Dict[str, Any]]:
    if not _table_exists('ROLE'):
        return []
    return _safe_rows(
        """
        SELECT ROLE_ID AS role_id, ROLE_CODE AS role_code,
               ROLE_NAME AS role_name, DESCRIPTION AS description
        FROM ROLE WHERE IS_ACTIVE = 1
        ORDER BY ROLE_NAME
        """,
        {},
    )


def assign_user_role(user_id: int, role_code: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _table_exists('ROLE') or not _table_exists('USER_ROLE'):
        return False, 'RBAC tables not available', None
    users = _safe_rows(
        'SELECT USER_ID FROM APP_USER WHERE USER_ID = :user_id AND IS_ACTIVE = 1',
        {'user_id': int(user_id)},
    )
    if not users:
        return False, 'User not found', None
    roles = _safe_rows(
        'SELECT ROLE_ID FROM ROLE WHERE ROLE_CODE = :role_code AND IS_ACTIVE = 1',
        {'role_code': role_code.strip().upper()},
    )
    if not roles:
        return False, 'Role not found', None
    role_id = int(roles[0]['role_id'])
    existing = _safe_rows(
        'SELECT USER_ROLE_ID FROM USER_ROLE WHERE USER_ID = :user_id AND ROLE_ID = :role_id',
        {'user_id': int(user_id), 'role_id': role_id},
    )
    if existing:
        role_rows = _safe_rows(
            """
            SELECT r.ROLE_CODE AS role_code
            FROM USER_ROLE ur JOIN ROLE r ON r.ROLE_ID = ur.ROLE_ID
            WHERE ur.USER_ID = :user_id
            """,
            {'user_id': int(user_id)},
        )
        return True, 'Role already assigned', {
            'user_id': user_id,
            'roles': [r['role_code'] for r in role_rows],
        }
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT SEQ_USER_ROLE_ID.NEXTVAL AS id FROM DUAL')
                ur_id = int((cur.fetchone() or [0])[0])
                cur.execute(
                    """
                    INSERT INTO USER_ROLE (USER_ROLE_ID, USER_ID, ROLE_ID, CREATED_AT)
                    VALUES (:ur_id, :user_id, :role_id, SYSTIMESTAMP)
                    """,
                    {'ur_id': ur_id, 'user_id': int(user_id), 'role_id': role_id},
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None
    role_rows = _safe_rows(
        """
        SELECT r.ROLE_CODE AS role_code
        FROM USER_ROLE ur JOIN ROLE r ON r.ROLE_ID = ur.ROLE_ID
        WHERE ur.USER_ID = :user_id
        """,
        {'user_id': int(user_id)},
    )
    return True, 'Role assigned', {
        'user_id': user_id,
        'roles': [r['role_code'] for r in role_rows],
    }


def save_category(payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    mode = (payload.get('mode') or '').strip().lower()
    flag = (payload.get('flag') or '').strip().upper()[:1]
    loc = resolve_location_code(payload.get('location_code'))
    name = (payload.get('name') or '').strip()
    if not name:
        return False, 'Name is required', None

    if mode == 'update':
        code = payload.get('code')
        if code is None:
            return False, 'Code is required', None
        ok, err = update_category_master_name(int(code), flag, name, location_code=loc)
        if not ok:
            return False, err or 'Update failed', None
        return True, 'Category updated', {'code': int(code), 'flag': flag, 'name': name.upper()}

    if mode != 'create':
        return False, 'Invalid mode', None

    if flag == 'M':
        ok, err, new_code = insert_category_main(name, loc)
    elif flag == 'D':
        main_code = payload.get('main_code')
        if main_code is None:
            return False, 'Main category code is required', None
        ok, err, new_code = insert_category_dept(name, int(main_code), loc)
    elif flag == 'C':
        d_code = payload.get('d_code')
        if d_code is None:
            return False, 'Department code is required', None
        ok, err, new_code = insert_category_micro(name, int(d_code), loc)
    else:
        return False, 'Invalid category level', None

    if not ok or new_code is None:
        return False, err or 'Insert failed', None
    return True, 'Category created', {'code': new_code, 'flag': flag, 'name': name.upper()}


def list_media(*, placement: Optional[str] = None) -> List[Dict[str, Any]]:
    rows, _warning = media_db.list_media(placement=placement, active_only=False)
    return rows


def upsert_media(payload: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    body = {
        'media_id': payload.get('media_id'),
        'placement': payload['placement'],
        'ref_key': payload.get('ref_key'),
        'title': payload.get('title'),
        'subtitle': payload.get('subtitle'),
        'title_ar': payload.get('title_ar'),
        'subtitle_ar': payload.get('subtitle_ar'),
        'image_url': media_svc.normalize_image_url(payload['image_url']),
        'link_url': payload.get('link_url'),
        'alt_text': payload.get('alt_text'),
        'sort_order': int(payload.get('sort_order') or 0),
        'meta': payload.get('meta') or {},
        'is_active': bool(payload.get('is_active', True)),
    }
    return media_db.upsert_media(body)


def deactivate_media(media_id: int) -> Tuple[bool, str]:
    return media_db.deactivate_media(media_id)


def list_pending_reviews(*, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, total, _ = reviews_db.list_reviews(page=page, page_size=page_size, status='PENDING')
    meta = build_pagination_meta(page=page, page_size=page_size, total_records=total)
    return rows, meta


def moderate_review(review_id: int, status: str) -> Tuple[bool, str]:
    return reviews_db.update_review_status(review_id, status)
