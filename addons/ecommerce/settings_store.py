"""Persisted storefront settings (JSON file per location)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from nexa_http import session

from addons.ecommerce.services.common import resolve_location_code

_ADDON_ROOT = Path(__file__).resolve().parents[1]
_SETTINGS_DIR = _ADDON_ROOT / 'data' / 'settings'

DEFAULT_SETTINGS: Dict[str, Any] = {
    'store_name': 'MamaHub',
    'store_email': 'hello@mamahub.store',
    'store_phone': '+974 0000 0000',
    'store_address': 'Doha, Qatar',
    'currency_code': 'QAR',
    'timezone': 'Asia/Qatar',
    'tax_rate': 0.0,
    'checkout_enabled': True,
    'pickup_enabled': True,
    'delivery_enabled': True,
    'coupons_enabled': False,
    'show_all_items_on_web': False,
}


def show_all_items_on_web() -> bool:
    return bool(load_store_settings().get('show_all_items_on_web'))


def coupons_enabled() -> bool:
    return bool(load_store_settings().get('coupons_enabled'))


def _settings_path() -> Path:
    loc = resolve_location_code()
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _SETTINGS_DIR / f'settings_loc_{loc}.json'


def load_store_settings() -> Dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        data = dict(DEFAULT_SETTINGS)
        data['location_code'] = resolve_location_code()
        return data
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            raw = {}
    except (json.JSONDecodeError, OSError):
        raw = {}
    merged = {**DEFAULT_SETTINGS, **raw}
    merged['location_code'] = resolve_location_code()
    return merged


def save_store_settings(values: Dict[str, Any]) -> None:
    payload = {**load_store_settings(), **values}
    payload['location_code'] = resolve_location_code()
    payload['updated_by'] = session.get('user')
    path = _settings_path()
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
