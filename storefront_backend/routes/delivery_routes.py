"""Delivery and pickup lookup routes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from storefront_backend.services import delivery as delivery_svc
from storefront_backend.services import geocoding as geocoding_svc
from storefront_backend.services import promotions as promo_svc
from storefront_backend.utils.response import success_response

router = APIRouter(tags=['Delivery & Pickup'])

DEFAULT_ETA_MIN = 60
DEFAULT_ETA_MAX = 75


def _estimate_for_coords(lat: float, lng: float, place: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    city = (place or {}).get('city') or 'Doha'
    area = (place or {}).get('area') or (place or {}).get('street') or 'Your area'
    zones = delivery_svc.list_zones(city=city) or delivery_svc.list_zones()
    zone = zones[0] if zones else None
    return {
        'latitude': lat,
        'longitude': lng,
        'area_label': area,
        'city': city,
        'street': (place or {}).get('street') or area,
        'country': (place or {}).get('country') or 'Qatar',
        'full_label': (place or {}).get('label') or f'{area}, {city}',
        'delivery_zone_id': zone.get('delivery_zone_id') if zone else None,
        'zone_name': zone.get('zone_name') if zone else None,
        'delivery_fee': float(zone.get('delivery_fee') or 0) if zone else 0,
        'eta_min_minutes': DEFAULT_ETA_MIN,
        'eta_max_minutes': DEFAULT_ETA_MAX,
        'delivery_available': True,
    }


@router.get('/delivery/geocode/search')
async def geocode_search(
    q: str = Query(..., min_length=2),
    country: str = Query('qa'),
):
    results = geocoding_svc.search_places(q, country=country)
    return success_response(data=results, message='Places retrieved')


@router.get('/delivery/geocode/reverse')
async def geocode_reverse(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    place = geocoding_svc.reverse_geocode(lat, lng)
    if not place:
        return success_response(
            data=_estimate_for_coords(lat, lng),
            message='Coordinates accepted with default area',
        )
    return success_response(
        data=_estimate_for_coords(lat, lng, place),
        message='Location resolved',
    )


@router.get('/delivery/estimate')
async def delivery_estimate(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    place = geocoding_svc.reverse_geocode(lat, lng)
    data = _estimate_for_coords(lat, lng, place)
    return success_response(data=data, message='Delivery estimate calculated')


@router.get('/delivery/zones')
async def list_delivery_zones(city: Optional[str] = Query(None)):
    data = delivery_svc.list_zones(city=city)
    return success_response(data=data, message='Delivery zones retrieved')


@router.get('/delivery/slots')
async def list_delivery_slots():
    data = delivery_svc.list_slots()
    return success_response(data=data, message='Delivery slots retrieved')


@router.get('/pickup/stores')
async def list_pickup_stores():
    data = delivery_svc.list_pickup_stores()
    return success_response(data=data, message='Pickup stores retrieved')


@router.get('/promotions/coupons')
async def list_coupons():
    data = promo_svc.list_public_coupons()
    return success_response(data=data, message='Coupons retrieved')
