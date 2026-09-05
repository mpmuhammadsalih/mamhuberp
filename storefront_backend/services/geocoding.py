"""OpenStreetMap Nominatim geocoding."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

NOMINATIM_BASE = 'https://nominatim.openstreetmap.org'
USER_AGENT = 'MamaHubToyStore/1.0 (delivery-location)'


def _headers() -> Dict[str, str]:
    return {'User-Agent': USER_AGENT, 'Accept-Language': 'en'}


def _map_search_row(row: Dict[str, Any]) -> Dict[str, Any]:
    address = row.get('address') or {}
    area = (
        address.get('suburb')
        or address.get('neighbourhood')
        or address.get('quarter')
        or address.get('city_district')
        or address.get('town')
        or address.get('village')
        or ''
    )
    city = address.get('city') or address.get('town') or address.get('state') or 'Doha'
    street = address.get('road') or address.get('pedestrian') or address.get('footway') or ''
    building = address.get('house_number') or ''
    street_line = ' '.join(part for part in (building, street) if part).strip() or row.get('name') or area

    return {
        'label': row.get('display_name') or street_line or area or city,
        'latitude': float(row.get('lat') or 0),
        'longitude': float(row.get('lon') or 0),
        'area': area,
        'city': city,
        'street': street_line or row.get('display_name', ''),
        'country': address.get('country') or 'Qatar',
    }


def search_places(query: str, *, country: str = 'qa', limit: int = 6) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    params = {
        'q': query.strip(),
        'format': 'json',
        'addressdetails': 1,
        'limit': limit,
        'countrycodes': country,
        'accept-language': 'en',
    }
    try:
        response = requests.get(
            f'{NOMINATIM_BASE}/search',
            params=params,
            headers=_headers(),
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json()
    except Exception:  # noqa: BLE001
        return []
    return [_map_search_row(row) for row in rows]


def reverse_geocode(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    params = {
        'lat': lat,
        'lon': lng,
        'format': 'json',
        'addressdetails': 1,
        'zoom': 18,
        'accept-language': 'en',
    }
    try:
        response = requests.get(
            f'{NOMINATIM_BASE}/reverse',
            params=params,
            headers=_headers(),
            timeout=10,
        )
        response.raise_for_status()
        row = response.json()
    except Exception:  # noqa: BLE001
        return None
    if not row or row.get('error'):
        return None
    return _map_search_row(row)
