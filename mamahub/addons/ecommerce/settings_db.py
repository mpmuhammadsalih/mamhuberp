"""Delivery/checkout settings from MH_* tables."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import oracledb

from db import _get_connection, _safe_rows, _table_exists

ZONE_TABLE = 'MH_DELIVERY_ZONE'
SLOT_TABLE = 'MH_DELIVERY_SLOT'
PICKUP_TABLE = 'MH_PICKUP_STORE'


def _next_row_id(cur, *, sequence: str, table: str, id_column: str) -> int:
    try:
        cur.execute(f'SELECT {sequence}.NEXTVAL AS id FROM DUAL')
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except oracledb.DatabaseError:
        pass
    cur.execute(f'SELECT NVL(MAX({id_column}), 0) + 1 AS id FROM {table}')
    row = cur.fetchone()
    return int(row[0] if row else 1)


def _slug_code(value: str, *, fallback: str = 'item', max_len: int = 40) -> str:
    raw = re.sub(r'[^A-Za-z0-9]+', '_', (value or '').strip().upper()).strip('_')
    if not raw:
        raw = fallback.upper()
    return raw[:max_len]


def delivery_tables_ready() -> bool:
    return _table_exists(ZONE_TABLE)


def _table_missing_message() -> str:
    return (
        'Delivery tables are not installed. '
        'Run MamaHub schema script sql/02_tables/11_mh_delivery_pickup.sql on the tenant DB.'
    )


def list_delivery_zones(*, include_inactive: bool = True) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not delivery_tables_ready():
        return [], _table_missing_message()
    where = '' if include_inactive else 'WHERE IS_ACTIVE = 1'
    rows = _safe_rows(
        f"""
        SELECT
            DELIVERY_ZONE_ID AS delivery_zone_id,
            ZONE_CODE AS zone_code,
            ZONE_NAME AS zone_name,
            CITY AS city,
            DELIVERY_FEE AS delivery_fee,
            MIN_ORDER_AMOUNT AS min_order_amount,
            FREE_DELIVERY_THRESHOLD AS free_delivery_threshold,
            ESTIMATED_DAYS AS estimated_days,
            IS_ACTIVE AS is_active
        FROM MH_DELIVERY_ZONE
        {where}
        ORDER BY CITY, ZONE_NAME
        """,
        {},
    )
    for row in rows:
        row['is_active'] = int(row.get('is_active') or 0) == 1
    return rows, None


def update_delivery_zone(
    zone_id: int,
    *,
    delivery_fee: float,
    min_order_amount: float,
    free_delivery_threshold: Optional[float],
    estimated_days: int,
    is_active: bool,
) -> Tuple[bool, str]:
    if not delivery_tables_ready():
        return False, _table_missing_message()
    existing = _safe_rows(
        'SELECT DELIVERY_ZONE_ID FROM MH_DELIVERY_ZONE WHERE DELIVERY_ZONE_ID = :zone_id',
        {'zone_id': int(zone_id)},
    )
    if not existing:
        return False, 'Delivery zone not found'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_DELIVERY_ZONE
                    SET DELIVERY_FEE = :delivery_fee,
                        MIN_ORDER_AMOUNT = :min_order_amount,
                        FREE_DELIVERY_THRESHOLD = :free_delivery_threshold,
                        ESTIMATED_DAYS = :estimated_days,
                        IS_ACTIVE = :is_active
                    WHERE DELIVERY_ZONE_ID = :zone_id
                    """,
                    {
                        'zone_id': int(zone_id),
                        'delivery_fee': delivery_fee,
                        'min_order_amount': min_order_amount,
                        'free_delivery_threshold': free_delivery_threshold,
                        'estimated_days': int(estimated_days),
                        'is_active': 1 if is_active else 0,
                    },
                )
            conn.commit()
        return True, 'Delivery zone updated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def create_delivery_zone(
    *,
    zone_code: str,
    zone_name: str,
    city: str,
    delivery_fee: float,
    min_order_amount: float,
    free_delivery_threshold: Optional[float],
    estimated_days: int,
    is_active: bool = True,
) -> Tuple[bool, str]:
    if not delivery_tables_ready():
        return False, _table_missing_message()
    code = _slug_code(zone_code or zone_name, fallback='zone')
    name = (zone_name or '').strip()
    city_name = (city or '').strip()
    if not name:
        return False, 'Zone name is required.'
    if not city_name:
        return False, 'City is required.'
    dup = _safe_rows(
        """
        SELECT DELIVERY_ZONE_ID FROM MH_DELIVERY_ZONE
        WHERE UPPER(ZONE_CODE) = UPPER(:zone_code)
        FETCH FIRST 1 ROWS ONLY
        """,
        {'zone_code': code},
    )
    if dup:
        return False, f'Zone code "{code}" already exists.'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                zone_id = _next_row_id(
                    cur,
                    sequence='SEQ_MH_DELIVERY_ZONE_ID',
                    table=ZONE_TABLE,
                    id_column='DELIVERY_ZONE_ID',
                )
                cur.execute(
                    """
                    INSERT INTO MH_DELIVERY_ZONE (
                        DELIVERY_ZONE_ID, ZONE_CODE, ZONE_NAME, CITY,
                        DELIVERY_FEE, MIN_ORDER_AMOUNT, FREE_DELIVERY_THRESHOLD,
                        ESTIMATED_DAYS, IS_ACTIVE
                    ) VALUES (
                        :zone_id, :zone_code, :zone_name, :city,
                        :delivery_fee, :min_order_amount, :free_delivery_threshold,
                        :estimated_days, :is_active
                    )
                    """,
                    {
                        'zone_id': zone_id,
                        'zone_code': code,
                        'zone_name': name,
                        'city': city_name,
                        'delivery_fee': delivery_fee,
                        'min_order_amount': min_order_amount,
                        'free_delivery_threshold': free_delivery_threshold,
                        'estimated_days': int(estimated_days),
                        'is_active': 1 if is_active else 0,
                    },
                )
            conn.commit()
        return True, f'Delivery zone "{name}" created'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def list_delivery_slots(*, include_inactive: bool = True) -> List[Dict[str, Any]]:
    if not _table_exists(SLOT_TABLE):
        return []
    where = '' if include_inactive else 'WHERE IS_ACTIVE = 1'
    rows = _safe_rows(
        f"""
        SELECT
            DELIVERY_SLOT_ID AS delivery_slot_id,
            SLOT_CODE AS slot_code,
            SLOT_LABEL AS slot_label,
            START_HOUR AS start_hour,
            END_HOUR AS end_hour,
            MAX_ORDERS AS max_orders,
            IS_ACTIVE AS is_active
        FROM MH_DELIVERY_SLOT
        {where}
        ORDER BY START_HOUR
        """,
        {},
    )
    for row in rows:
        row['is_active'] = int(row.get('is_active') or 0) == 1
    return rows


def toggle_delivery_slot(slot_id: int) -> Tuple[bool, str]:
    if not _table_exists(SLOT_TABLE):
        return False, 'Delivery slot table not available'
    rows = _safe_rows(
        'SELECT IS_ACTIVE FROM MH_DELIVERY_SLOT WHERE DELIVERY_SLOT_ID = :slot_id',
        {'slot_id': int(slot_id)},
    )
    if not rows:
        return False, 'Delivery slot not found'
    new_active = 0 if int(rows[0].get('is_active') or 0) == 1 else 1
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_DELIVERY_SLOT SET IS_ACTIVE = :is_active
                    WHERE DELIVERY_SLOT_ID = :slot_id
                    """,
                    {'slot_id': int(slot_id), 'is_active': new_active},
                )
            conn.commit()
        return True, 'Delivery slot updated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def create_delivery_slot(
    *,
    slot_code: str,
    slot_label: str,
    start_hour: int,
    end_hour: int,
    max_orders: int,
    is_active: bool = True,
) -> Tuple[bool, str]:
    if not _table_exists(SLOT_TABLE):
        return False, 'Delivery slot table not available'
    code = _slug_code(slot_code or slot_label, fallback='slot')
    label = (slot_label or '').strip()
    if not label:
        return False, 'Slot label is required.'
    if start_hour < 0 or start_hour > 23 or end_hour < 1 or end_hour > 24:
        return False, 'Hours must be between 0 and 24.'
    if end_hour <= start_hour:
        return False, 'End hour must be after start hour.'
    dup = _safe_rows(
        """
        SELECT DELIVERY_SLOT_ID FROM MH_DELIVERY_SLOT
        WHERE UPPER(SLOT_CODE) = UPPER(:slot_code)
        FETCH FIRST 1 ROWS ONLY
        """,
        {'slot_code': code},
    )
    if dup:
        return False, f'Slot code "{code}" already exists.'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                slot_id = _next_row_id(
                    cur,
                    sequence='SEQ_MH_DELIVERY_SLOT_ID',
                    table=SLOT_TABLE,
                    id_column='DELIVERY_SLOT_ID',
                )
                cur.execute(
                    """
                    INSERT INTO MH_DELIVERY_SLOT (
                        DELIVERY_SLOT_ID, SLOT_CODE, SLOT_LABEL,
                        START_HOUR, END_HOUR, MAX_ORDERS, IS_ACTIVE
                    ) VALUES (
                        :slot_id, :slot_code, :slot_label,
                        :start_hour, :end_hour, :max_orders, :is_active
                    )
                    """,
                    {
                        'slot_id': slot_id,
                        'slot_code': code,
                        'slot_label': label,
                        'start_hour': int(start_hour),
                        'end_hour': int(end_hour),
                        'max_orders': max(1, int(max_orders or 1)),
                        'is_active': 1 if is_active else 0,
                    },
                )
            conn.commit()
        return True, f'Delivery slot "{label}" created'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def list_pickup_stores(*, include_inactive: bool = True) -> List[Dict[str, Any]]:
    if not _table_exists(PICKUP_TABLE):
        return []
    where = '' if include_inactive else 'WHERE IS_ACTIVE = 1'
    rows = _safe_rows(
        f"""
        SELECT
            PICKUP_STORE_ID AS pickup_store_id,
            STORE_CODE AS store_code,
            STORE_NAME AS store_name,
            ADDRESS_LINE AS address_line,
            CITY AS city,
            OPEN_HOUR AS open_hour,
            CLOSE_HOUR AS close_hour,
            IS_ACTIVE AS is_active
        FROM MH_PICKUP_STORE
        {where}
        ORDER BY STORE_NAME
        """,
        {},
    )
    for row in rows:
        row['is_active'] = int(row.get('is_active') or 0) == 1
    return rows


def toggle_pickup_store(store_id: int) -> Tuple[bool, str]:
    if not _table_exists(PICKUP_TABLE):
        return False, 'Pickup store table not available'
    rows = _safe_rows(
        'SELECT IS_ACTIVE FROM MH_PICKUP_STORE WHERE PICKUP_STORE_ID = :store_id',
        {'store_id': int(store_id)},
    )
    if not rows:
        return False, 'Pickup store not found'
    new_active = 0 if int(rows[0].get('is_active') or 0) == 1 else 1
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_PICKUP_STORE SET IS_ACTIVE = :is_active
                    WHERE PICKUP_STORE_ID = :store_id
                    """,
                    {'store_id': int(store_id), 'is_active': new_active},
                )
            conn.commit()
        return True, 'Pickup store updated'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def create_pickup_store(
    *,
    store_code: str,
    store_name: str,
    address_line: str,
    city: str,
    open_hour: int,
    close_hour: int,
    is_active: bool = True,
) -> Tuple[bool, str]:
    if not _table_exists(PICKUP_TABLE):
        return False, 'Pickup store table not available'
    code = _slug_code(store_code or store_name, fallback='store')
    name = (store_name or '').strip()
    if not name:
        return False, 'Store name is required.'
    if open_hour < 0 or open_hour > 23 or close_hour < 1 or close_hour > 24:
        return False, 'Hours must be between 0 and 24.'
    if close_hour <= open_hour:
        return False, 'Close hour must be after open hour.'
    dup = _safe_rows(
        """
        SELECT PICKUP_STORE_ID FROM MH_PICKUP_STORE
        WHERE UPPER(STORE_CODE) = UPPER(:store_code)
        FETCH FIRST 1 ROWS ONLY
        """,
        {'store_code': code},
    )
    if dup:
        return False, f'Store code "{code}" already exists.'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                store_id = _next_row_id(
                    cur,
                    sequence='SEQ_MH_PICKUP_STORE_ID',
                    table=PICKUP_TABLE,
                    id_column='PICKUP_STORE_ID',
                )
                cur.execute(
                    """
                    INSERT INTO MH_PICKUP_STORE (
                        PICKUP_STORE_ID, STORE_CODE, STORE_NAME,
                        ADDRESS_LINE, CITY, OPEN_HOUR, CLOSE_HOUR, IS_ACTIVE
                    ) VALUES (
                        :store_id, :store_code, :store_name,
                        :address_line, :city, :open_hour, :close_hour, :is_active
                    )
                    """,
                    {
                        'store_id': store_id,
                        'store_code': code,
                        'store_name': name,
                        'address_line': (address_line or '').strip() or None,
                        'city': (city or '').strip() or None,
                        'open_hour': int(open_hour),
                        'close_hour': int(close_hour),
                        'is_active': 1 if is_active else 0,
                    },
                )
            conn.commit()
        return True, f'Pickup store "{name}" created'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
