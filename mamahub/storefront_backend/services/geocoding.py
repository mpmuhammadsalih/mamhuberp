"""OpenStreetMap Nominatim + Photon geocoding, localized to the shop language."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

NOMINATIM_BASE = 'https://nominatim.openstreetmap.org'
PHOTON_BASE = 'https://photon.komoot.io/api/'
USER_AGENT = 'MamaHubToyStore/1.0 (delivery-location)'

# Qatar bounding box: minLon, minLat, maxLon, maxLat
QATAR_BBOX = (50.7, 24.47, 51.64, 26.18)
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')

_CITY_FALLBACK = {'en': 'Doha', 'ar': 'الدوحة'}
_COUNTRY_FALLBACK = {'en': 'Qatar', 'ar': 'قطر'}


def normalize_lang(lang: Optional[str]) -> str:
    raw = (lang or 'en').strip().lower()
    if raw.startswith('ar'):
        return 'ar'
    return 'en'


def _headers(lang: str) -> Dict[str, str]:
    accept = 'ar,en;q=0.2' if lang == 'ar' else 'en-US,en;q=0.9,ar;q=0.1'
    return {'User-Agent': USER_AGENT, 'Accept-Language': accept}


def _has_arabic(text: str) -> bool:
    return bool(text and _ARABIC_RE.search(text))


def _pick_localized_name(namedetails: Dict[str, Any], lang: str, fallback: str = '') -> str:
    details = namedetails or {}
    if lang == 'ar':
        return (
            details.get('name:ar')
            or fallback
            or details.get('name')
            or ''
        )
    english = details.get('name:en') or details.get('name:en-US') or ''
    if english:
        return english
    if fallback and not _has_arabic(fallback):
        return fallback
    return details.get('name') if details.get('name') and not _has_arabic(str(details.get('name'))) else fallback


def _clean_parts(parts: List[str], lang: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for part in parts:
        text = (part or '').strip()
        if not text or text in seen:
            continue
        if lang == 'en' and _has_arabic(text):
            continue
        seen.add(text)
        out.append(text)
    return out


def _map_search_row(row: Dict[str, Any], lang: str) -> Dict[str, Any]:
    address = row.get('address') or {}
    namedetails = row.get('namedetails') or {}
    feature_name = _pick_localized_name(namedetails, lang, row.get('name') or '')

    area = (
        address.get('suburb')
        or address.get('neighbourhood')
        or address.get('quarter')
        or address.get('city_district')
        or address.get('town')
        or address.get('village')
        or ''
    )
    city = address.get('city') or address.get('town') or address.get('state') or ''
    street = address.get('road') or address.get('pedestrian') or address.get('footway') or ''
    building = address.get('house_number') or ''
    country = address.get('country') or ''

    if lang == 'en':
        if not city or _has_arabic(city):
            city = _CITY_FALLBACK['en'] if not city or city in ('الدوحة',) else city
            if _has_arabic(city):
                city = _CITY_FALLBACK['en']
        if not country or _has_arabic(country):
            country = _COUNTRY_FALLBACK['en']
        if area and _has_arabic(area):
            area = feature_name if feature_name and not _has_arabic(feature_name) else ''
        if street and _has_arabic(street):
            street = feature_name if feature_name and not _has_arabic(feature_name) else ''
    else:
        if not city or not _has_arabic(city) and city.lower() in ('doha',):
            city = city if city and _has_arabic(city) else _CITY_FALLBACK['ar']
        if not country or country.lower() == 'qatar':
            country = _COUNTRY_FALLBACK['ar']

    if not city:
        city = _CITY_FALLBACK[lang]
    if not country:
        country = _COUNTRY_FALLBACK[lang]

    street_line = ' '.join(part for part in (building, street) if part).strip() or feature_name or area
    display = row.get('display_name') or ''
    if lang == 'en' and _has_arabic(display):
        display = ''
    if lang == 'ar' and display and not _has_arabic(display) and feature_name:
        display = ''

    label = display or ', '.join(
        _clean_parts([street_line or feature_name, area, city, country], lang)
    )
    if not label:
        label = feature_name or area or city

    return {
        'label': label,
        'latitude': float(row.get('lat') or 0),
        'longitude': float(row.get('lon') or 0),
        'area': area or feature_name or city,
        'city': city,
        'street': street_line or label,
        'country': country,
    }


def _nominatim_search(query: str, country: str, limit: int, lang: str) -> List[Dict[str, Any]]:
    min_lon, min_lat, max_lon, max_lat = QATAR_BBOX
    params = {
        'q': query.strip(),
        'format': 'json',
        'addressdetails': 1,
        'namedetails': 1,
        'limit': limit,
        'countrycodes': country,
        'accept-language': 'ar' if lang == 'ar' else 'en',
        'viewbox': f'{min_lon},{max_lat},{max_lon},{min_lat}',
        'bounded': 0,
    }
    response = requests.get(
        f'{NOMINATIM_BASE}/search',
        params=params,
        headers=_headers(lang),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return [_map_search_row(row, lang) for row in rows if isinstance(row, dict)]


def _photon_search(query: str, limit: int, lang: str) -> List[Dict[str, Any]]:
    # Photon only accepts a subset of languages; Arabic returns 400.
    params: Dict[str, Any] = {
        'q': query.strip(),
        'lat': 25.2854,
        'lon': 51.531,
        'limit': max(limit, 8),
        'bbox': ','.join(str(v) for v in QATAR_BBOX),
    }
    if lang != 'ar':
        params['lang'] = 'en'
    response = requests.get(PHOTON_BASE, params=params, headers=_headers(lang), timeout=10)
    response.raise_for_status()
    features = (response.json() or {}).get('features') or []
    results: List[Dict[str, Any]] = []
    for feature in features:
        props = feature.get('properties') or {}
        geometry = feature.get('geometry') or {}
        coords = geometry.get('coordinates') or [0, 0]
        lon = float(coords[0] if len(coords) > 0 else 0)
        lat = float(coords[1] if len(coords) > 1 else 0)
        country = props.get('country') or _COUNTRY_FALLBACK[lang]
        if country and 'qatar' not in country.lower() and country != 'قطر':
            continue
        name = props.get('name') or props.get('street') or ''
        city = props.get('city') or props.get('district') or _CITY_FALLBACK[lang]
        area = props.get('district') or props.get('locality') or name
        street = props.get('street') or name
        if lang == 'ar':
            if not _has_arabic(city):
                city = _CITY_FALLBACK['ar'] if city.lower() in ('doha', '') else city
            if not _has_arabic(country):
                country = _COUNTRY_FALLBACK['ar']
        else:
            if _has_arabic(city):
                city = _CITY_FALLBACK['en']
            if _has_arabic(country):
                country = _COUNTRY_FALLBACK['en']
        label = ', '.join(_clean_parts([name or street, area, city, country], lang)) or name or city
        results.append({
            'label': label,
            'latitude': lat,
            'longitude': lon,
            'area': area or city,
            'city': city,
            'street': street or label,
            'country': country,
        })
        if len(results) >= limit:
            break
    return results


def search_places(
    query: str,
    *,
    country: str = 'qa',
    limit: int = 6,
    lang: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    locale = normalize_lang(lang)
    last_error: Optional[Exception] = None
    try:
        rows = _nominatim_search(query, country, limit, locale)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        logger.warning('Nominatim search failed for %r: %s', query, exc)

    try:
        rows = _photon_search(query, limit, locale)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        logger.warning('Photon search failed for %r: %s', query, exc)

    if last_error:
        logger.warning('Place search returned no results for %r', query)
    return []


def reverse_geocode(lat: float, lng: float, *, lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    locale = normalize_lang(lang)
    params = {
        'lat': lat,
        'lon': lng,
        'format': 'json',
        'addressdetails': 1,
        'namedetails': 1,
        'zoom': 18,
        'accept-language': 'ar' if locale == 'ar' else 'en',
    }
    try:
        response = requests.get(
            f'{NOMINATIM_BASE}/reverse',
            params=params,
            headers=_headers(locale),
            timeout=10,
        )
        response.raise_for_status()
        row = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning('Nominatim reverse failed: %s', exc)
        return None
    if not row or row.get('error'):
        return None
    return _map_search_row(row, locale)
