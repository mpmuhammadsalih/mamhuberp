"""Customer address CRUD."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from db import _get_connection, _safe_rows, _table_exists
from storefront_backend.services.schema_bootstrap import ensure_address_schema


def _ready() -> bool:
    if _table_exists('MH_CUSTOMER_ADDRESS'):
        return True
    try:
        ensure_address_schema()
    except Exception:
        return False
    return _table_exists('MH_CUSTOMER_ADDRESS')


def _next_id() -> int:
    rows = _safe_rows('SELECT SEQ_MH_ADDRESS_ID.NEXTVAL AS id FROM DUAL', {})
    return int(rows[0]['id'])


def _to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    lat = row.get('latitude')
    lng = row.get('longitude')
    return {
        'address_id': int(row['address_id']),
        'address_title': row.get('address_title'),
        'address_type': row.get('address_type') or 'HOME',
        'building_number': row.get('building_number'),
        'street': row.get('street'),
        'zone': row.get('zone'),
        'area': row.get('area'),
        'city': row.get('city'),
        'country': row.get('country'),
        'landmark': row.get('landmark'),
        'latitude': float(lat) if lat is not None else None,
        'longitude': float(lng) if lng is not None else None,
        'is_default': int(row.get('is_default') or 0) == 1,
    }


def list_addresses(user_id: int) -> List[Dict[str, Any]]:
    if not _ready():
        return []
    rows = _safe_rows(
        """
        SELECT
            ADDRESS_ID AS address_id,
            ADDRESS_TITLE AS address_title,
            ADDRESS_TYPE AS address_type,
            BUILDING_NUMBER AS building_number,
            STREET AS street,
            ZONE AS zone,
            AREA AS area,
            CITY AS city,
            COUNTRY AS country,
            LANDMARK AS landmark,
            LATITUDE AS latitude,
            LONGITUDE AS longitude,
            IS_DEFAULT AS is_default
        FROM MH_CUSTOMER_ADDRESS
        WHERE USER_ID = :user_id AND IS_ACTIVE = 1
        ORDER BY IS_DEFAULT DESC, ADDRESS_ID DESC
        """,
        {'user_id': int(user_id)},
    )
    return [_to_dict(row) for row in rows]


def get_address(user_id: int, address_id: int) -> Optional[Dict[str, Any]]:
    if not _ready():
        return None
    rows = _safe_rows(
        """
        SELECT
            ADDRESS_ID AS address_id,
            ADDRESS_TITLE AS address_title,
            ADDRESS_TYPE AS address_type,
            BUILDING_NUMBER AS building_number,
            STREET AS street,
            ZONE AS zone,
            AREA AS area,
            CITY AS city,
            COUNTRY AS country,
            LANDMARK AS landmark,
            LATITUDE AS latitude,
            LONGITUDE AS longitude,
            IS_DEFAULT AS is_default
        FROM MH_CUSTOMER_ADDRESS
        WHERE USER_ID = :user_id AND ADDRESS_ID = :address_id AND IS_ACTIVE = 1
        """,
        {'user_id': int(user_id), 'address_id': int(address_id)},
    )
    return _to_dict(rows[0]) if rows else None


def serialize_address_snapshot(address: Dict[str, Any]) -> str:
    return json.dumps({
        'address_id': address.get('address_id'),
        'address_title': address.get('address_title'),
        'street': address.get('street'),
        'city': address.get('city'),
        'country': address.get('country'),
        'zone': address.get('zone'),
        'area': address.get('area'),
        'landmark': address.get('landmark'),
    })


def _clear_default(user_id: int, *, cur) -> None:
    cur.execute(
        """
        UPDATE MH_CUSTOMER_ADDRESS
        SET IS_DEFAULT = 0, MODIFIED_AT = SYSTIMESTAMP
        WHERE USER_ID = :user_id AND IS_DEFAULT = 1
        """,
        {'user_id': int(user_id)},
    )


def create_address(user_id: int, data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Address table not available', None
    address_id = _next_id()
    is_default = 1 if data.get('is_default') else 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if is_default:
                    _clear_default(user_id, cur=cur)
                cur.execute(
                    """
                    INSERT INTO MH_CUSTOMER_ADDRESS (
                        ADDRESS_ID, USER_ID, ADDRESS_TITLE, ADDRESS_TYPE,
                        BUILDING_NUMBER, STREET, ZONE, AREA, CITY, COUNTRY,
                        LANDMARK, LATITUDE, LONGITUDE, IS_DEFAULT, IS_ACTIVE,
                        CREATED_AT, CREATED_BY
                    ) VALUES (
                        :address_id, :user_id, :address_title, :address_type,
                        :building_number, :street, :zone, :area, :city, :country,
                        :landmark, :latitude, :longitude, :is_default, 1,
                        SYSTIMESTAMP, :created_by
                    )
                    """,
                    {
                        'address_id': address_id,
                        'user_id': int(user_id),
                        'address_title': data['address_title'],
                        'address_type': data.get('address_type') or 'HOME',
                        'building_number': data.get('building_number'),
                        'street': data['street'],
                        'zone': data.get('zone'),
                        'area': data.get('area'),
                        'city': data['city'],
                        'country': data.get('country') or 'Qatar',
                        'landmark': data.get('landmark'),
                        'latitude': data.get('latitude'),
                        'longitude': data.get('longitude'),
                        'is_default': is_default,
                        'created_by': int(user_id),
                    },
                )
            conn.commit()
        created = get_address(user_id, address_id)
        return True, 'Address created successfully', created
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def update_address(
    user_id: int,
    address_id: int,
    updates: Dict[str, Any],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Address table not available', None
    existing = get_address(user_id, address_id)
    if not existing:
        return False, 'Address not found', None

    fields = {
        'address_title': updates.get('address_title', existing['address_title']),
        'address_type': updates.get('address_type', existing['address_type']),
        'building_number': updates.get('building_number', existing['building_number']),
        'street': updates.get('street', existing['street']),
        'zone': updates.get('zone', existing['zone']),
        'area': updates.get('area', existing['area']),
        'city': updates.get('city', existing['city']),
        'country': updates.get('country', existing['country']),
        'landmark': updates.get('landmark', existing['landmark']),
        'latitude': updates.get('latitude', existing['latitude']),
        'longitude': updates.get('longitude', existing['longitude']),
    }
    is_default = existing['is_default']
    if 'is_default' in updates:
        is_default = bool(updates['is_default'])

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if is_default:
                    _clear_default(user_id, cur=cur)
                cur.execute(
                    """
                    UPDATE MH_CUSTOMER_ADDRESS
                    SET ADDRESS_TITLE = :address_title,
                        ADDRESS_TYPE = :address_type,
                        BUILDING_NUMBER = :building_number,
                        STREET = :street,
                        ZONE = :zone,
                        AREA = :area,
                        CITY = :city,
                        COUNTRY = :country,
                        LANDMARK = :landmark,
                        LATITUDE = :latitude,
                        LONGITUDE = :longitude,
                        IS_DEFAULT = :is_default,
                        MODIFIED_AT = SYSTIMESTAMP,
                        MODIFIED_BY = :modified_by
                    WHERE ADDRESS_ID = :address_id AND USER_ID = :user_id
                    """,
                    {
                        **fields,
                        'is_default': 1 if is_default else 0,
                        'address_id': int(address_id),
                        'user_id': int(user_id),
                        'modified_by': int(user_id),
                    },
                )
            conn.commit()
        updated = get_address(user_id, address_id)
        return True, 'Address updated successfully', updated
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def delete_address(user_id: int, address_id: int) -> Tuple[bool, str]:
    if not _ready():
        return False, 'Address table not available'
    existing = get_address(user_id, address_id)
    if not existing:
        return False, 'Address not found'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE MH_CUSTOMER_ADDRESS
                    SET IS_ACTIVE = 0, IS_DEFAULT = 0, MODIFIED_AT = SYSTIMESTAMP
                    WHERE ADDRESS_ID = :address_id AND USER_ID = :user_id
                    """,
                    {'address_id': int(address_id), 'user_id': int(user_id)},
                )
            conn.commit()
        return True, 'Address deleted successfully'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def set_default_address(user_id: int, address_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not _ready():
        return False, 'Address table not available', None
    existing = get_address(user_id, address_id)
    if not existing:
        return False, 'Address not found', None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                _clear_default(user_id, cur=cur)
                cur.execute(
                    """
                    UPDATE MH_CUSTOMER_ADDRESS
                    SET IS_DEFAULT = 1, MODIFIED_AT = SYSTIMESTAMP
                    WHERE ADDRESS_ID = :address_id AND USER_ID = :user_id
                    """,
                    {'address_id': int(address_id), 'user_id': int(user_id)},
                )
            conn.commit()
        updated = get_address(user_id, address_id)
        return True, 'Default address updated', updated
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None
