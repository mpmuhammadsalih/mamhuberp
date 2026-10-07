"""Delivery zones, slots, and pickup stores."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db import (
    _safe_rows,
    _table_exists,
    get_location_master_row,
    get_locations_list,
    list_location_master_rows,
)
from storefront_backend.services.schema_bootstrap import ensure_delivery_schema


def _row_value(row: Dict[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] is not None:
            return lowered[key.lower()]
    return None


def _map_locationmaster_pickup(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    code = _row_value(row, 'LOCATIONCODE', 'locationcode')
    if code is None:
        return None
    try:
        location_code = int(code)
    except (TypeError, ValueError):
        return None

    name = _row_value(row, 'LOCATIONNAME', 'locationname') or f'Store {location_code}'
    address = _row_value(row, 'ADDRESS', 'address')
    city = _row_value(row, 'CITY', 'city')
    phone = _row_value(row, 'TELEPHONE', 'telephone')
    db_code = _row_value(row, 'DBCODE', 'dbcode')

    return {
        'pickup_store_id': location_code,
        'store_code': str(db_code or location_code),
        'store_name': str(name).strip(),
        'address_line': str(address).strip() if address else None,
        'city': str(city).strip() if city else None,
        'telephone': str(phone).strip() if phone else None,
        'open_hour': 9,
        'close_hour': 21,
        'source': 'LOCATIONMASTER',
    }


def _locationmaster_pickup_rows() -> List[Dict[str, Any]]:
    stores: List[Dict[str, Any]] = []
    seen: set[int] = set()

    for row in list_location_master_rows() or []:
        mapped = _map_locationmaster_pickup(dict(row))
        if not mapped:
            continue
        store_id = int(mapped['pickup_store_id'])
        if store_id in seen:
            continue
        seen.add(store_id)
        stores.append(mapped)

    if stores:
        return stores

    for row in get_locations_list() or []:
        mapped = _map_locationmaster_pickup({
            'LOCATIONCODE': row.get('code'),
            'LOCATIONNAME': row.get('name'),
        })
        if not mapped:
            continue
        store_id = int(mapped['pickup_store_id'])
        if store_id in seen:
            continue
        seen.add(store_id)
        stores.append(mapped)

    return stores


def _mh_pickup_rows(*, active_only: bool) -> List[Dict[str, Any]]:
    if not _table_exists('MH_PICKUP_STORE'):
        return []
    where = 'WHERE IS_ACTIVE = 1' if active_only else ''
    return _safe_rows(
        f"""
        SELECT PICKUP_STORE_ID AS pickup_store_id,
               STORE_CODE AS store_code,
               STORE_NAME AS store_name,
               ADDRESS_LINE AS address_line,
               CITY AS city,
               OPEN_HOUR AS open_hour,
               CLOSE_HOUR AS close_hour
        FROM MH_PICKUP_STORE
        {where}
        ORDER BY STORE_NAME
        """,
        {},
    )


def list_zones(*, city: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_delivery_schema()
    if not _table_exists('MH_DELIVERY_ZONE'):
        return []
    if city:
        return _safe_rows(
            """
            SELECT DELIVERY_ZONE_ID AS delivery_zone_id,
                   ZONE_CODE AS zone_code,
                   ZONE_NAME AS zone_name,
                   CITY AS city,
                   DELIVERY_FEE AS delivery_fee,
                   MIN_ORDER_AMOUNT AS min_order_amount,
                   FREE_DELIVERY_THRESHOLD AS free_delivery_threshold,
                   ESTIMATED_DAYS AS estimated_days
            FROM MH_DELIVERY_ZONE
            WHERE IS_ACTIVE = 1 AND UPPER(CITY) = UPPER(:city)
            ORDER BY ZONE_NAME
            """,
            {'city': city},
        )
    return _safe_rows(
        """
        SELECT DELIVERY_ZONE_ID AS delivery_zone_id,
               ZONE_CODE AS zone_code,
               ZONE_NAME AS zone_name,
               CITY AS city,
               DELIVERY_FEE AS delivery_fee,
               MIN_ORDER_AMOUNT AS min_order_amount,
               FREE_DELIVERY_THRESHOLD AS free_delivery_threshold,
               ESTIMATED_DAYS AS estimated_days
        FROM MH_DELIVERY_ZONE
        WHERE IS_ACTIVE = 1
        ORDER BY CITY, ZONE_NAME
        """,
        {},
    )


def get_zone(zone_id: int) -> Optional[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT DELIVERY_ZONE_ID AS delivery_zone_id,
               ZONE_CODE AS zone_code,
               ZONE_NAME AS zone_name,
               CITY AS city,
               DELIVERY_FEE AS delivery_fee,
               MIN_ORDER_AMOUNT AS min_order_amount,
               FREE_DELIVERY_THRESHOLD AS free_delivery_threshold,
               ESTIMATED_DAYS AS estimated_days
        FROM MH_DELIVERY_ZONE
        WHERE DELIVERY_ZONE_ID = :zone_id AND IS_ACTIVE = 1
        """,
        {'zone_id': int(zone_id)},
    )
    return dict(rows[0]) if rows else None


def list_slots() -> List[Dict[str, Any]]:
    ensure_delivery_schema()
    if not _table_exists('MH_DELIVERY_SLOT'):
        return []
    return _safe_rows(
        """
        SELECT DELIVERY_SLOT_ID AS delivery_slot_id,
               SLOT_CODE AS slot_code,
               SLOT_LABEL AS slot_label,
               START_HOUR AS start_hour,
               END_HOUR AS end_hour
        FROM MH_DELIVERY_SLOT
        WHERE IS_ACTIVE = 1
        ORDER BY START_HOUR
        """,
        {},
    )


def get_slot(slot_id: int) -> Optional[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT DELIVERY_SLOT_ID AS delivery_slot_id,
               SLOT_CODE AS slot_code,
               SLOT_LABEL AS slot_label
        FROM MH_DELIVERY_SLOT
        WHERE DELIVERY_SLOT_ID = :slot_id AND IS_ACTIVE = 1
        """,
        {'slot_id': int(slot_id)},
    )
    return dict(rows[0]) if rows else None


def list_pickup_stores() -> List[Dict[str, Any]]:
    stores = _mh_pickup_rows(active_only=True)
    if stores:
        return stores
    return _locationmaster_pickup_rows()


def get_pickup_store(store_id: int) -> Optional[Dict[str, Any]]:
    if _table_exists('MH_PICKUP_STORE'):
        rows = _safe_rows(
            """
            SELECT PICKUP_STORE_ID AS pickup_store_id,
                   STORE_CODE AS store_code,
                   STORE_NAME AS store_name,
                   ADDRESS_LINE AS address_line,
                   CITY AS city
            FROM MH_PICKUP_STORE
            WHERE PICKUP_STORE_ID = :store_id AND IS_ACTIVE = 1
            """,
            {'store_id': int(store_id)},
        )
        if rows:
            return dict(rows[0])

    row = get_location_master_row(int(store_id))
    if row:
        return _map_locationmaster_pickup(dict(row))

    for store in _locationmaster_pickup_rows():
        if int(store['pickup_store_id']) == int(store_id):
            return store
    return None
