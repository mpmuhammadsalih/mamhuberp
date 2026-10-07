"""POS HTML cache busting and no-store headers for counter/kiosk browsers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

_ADDON_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _ADDON_ROOT.parents[1]
_TEMPLATE_DIR = _ADDON_ROOT / 'views' / 'templates' / 'pos_billing'
_STATIC_POS_FILES = (
    _PROJECT_ROOT / 'static' / 'js' / 'pos_billing.js',
    _PROJECT_ROOT / 'static' / 'js' / 'pos_shop.js',
    _PROJECT_ROOT / 'static' / 'css' / 'pos_shop.css',
    _PROJECT_ROOT / 'static' / 'js' / 'pos_price_edited_report.js',
    _PROJECT_ROOT / 'static' / 'js' / 'qz_invoice_print.js',
    _PROJECT_ROOT / 'static' / 'js' / 'qz_printer_prefs.js',
)


def _iter_version_paths() -> Iterable[Path]:
    if _TEMPLATE_DIR.is_dir():
        yield from _TEMPLATE_DIR.rglob('*.html')
    for path in _STATIC_POS_FILES:
        if path.is_file():
            yield path


def get_pos_asset_version() -> str:
    """Version token from newest POS template/static mtime (changes on deploy/edit)."""
    latest = 0.0
    for path in _iter_version_paths():
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    if latest <= 0:
        return '1'
    return str(int(latest))


def is_pos_html_page_path(path: str) -> bool:
    if not path.startswith('/pos-billing'):
        return False
    if '/api/' in path:
        return False
    return True


def _response_is_html(response: Any) -> bool:
    media = (getattr(response, 'media_type', None) or '').lower()
    if 'html' in media:
        return True
    return type(response).__name__ == 'TemplateResponse'


def apply_pos_page_no_cache_headers(response: Any) -> Any:
    headers = getattr(response, 'headers', None)
    if headers is None:
        return response
    headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    headers['Pragma'] = 'no-cache'
    headers['Expires'] = '0'
    return response
