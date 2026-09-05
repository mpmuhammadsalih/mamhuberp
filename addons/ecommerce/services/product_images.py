"""Bulk product image import for ecommerce Products (ITEMMASTER.IMAGE_PATH)."""
from __future__ import annotations

import html
import io
import os
import re
import time
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from nexa_http import current_app, url_for

from addons.ecommerce.services.common import resolve_location_code
from db import (
    _safe_rows,
    ensure_itemmaster_image_path_column,
    get_item_by_alternate_barcode,
    get_item_by_code,
    get_item_by_manufacturer_id,
    set_item_image_path,
)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

_ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
_MAX_ROWS = 2000
_MAX_EXCEL_BYTES = 50 * 1024 * 1024
_MAX_ZIP_BYTES = 50 * 1024 * 1024
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_DOWNLOAD_TIMEOUT_SEC = 30
_WEB_SEARCH_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
_BAD_IMAGE_URL_PARTS = (
    'gold-price',
    'gold price',
    'silver-rate',
    'exchangerates',
    'financialexpress',
    'stock-photo',
    'shutterstock',
    'gettyimages',
    'istockphoto',
    'depositphotos',
)
_PREFERRED_IMAGE_HOSTS = (
    'media-amazon.com',
    'walmartimages.com',
    'noon.com',
    'partycity.com',
    'onlinepartysupplies',
    'party.my',
    'celebrationstation',
    'target.com',
    'i5.walmartimages.com',
)


def _norm_key(value: Any) -> str:
    return ''.join(ch for ch in str(value or '').strip().lower() if ch.isalnum())


def _cell_str(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _format_to_ext(fmt: str, path_hint: str = '') -> str:
    token = str(fmt or path_hint or '').strip().lower().lstrip('.')
    mapping = {
        'png': '.png',
        'jpeg': '.jpg',
        'jpg': '.jpg',
        'gif': '.gif',
        'webp': '.webp',
    }
    if token in mapping:
        return mapping[token]
    ext = os.path.splitext(path_hint)[1].lower()
    if ext in _ALLOWED_IMAGE_EXT:
        return ext
    return '.jpg'


def _image_anchor_row_col(anchor: Any) -> Tuple[Optional[int], Optional[int]]:
    """Return 1-based Excel row and 0-based column for an embedded image anchor."""
    if anchor is None:
        return (None, None)
    if isinstance(anchor, str):
        return (None, None)
    origin = getattr(anchor, '_from', None)
    if origin is None:
        return (None, None)
    try:
        row = int(getattr(origin, 'row', 0)) + 1
        col = int(getattr(origin, 'col', 0))
        return (row, col)
    except (TypeError, ValueError):
        return (None, None)


def _header_image_col_index(headers: List[str]) -> int:
    aliases = {_norm_key(name) for name in ('Image', 'ProductImage', 'Picture', 'Photo')}
    for idx, header in enumerate(headers):
        if _norm_key(header) in aliases:
            return idx
    return -1


def _extract_embedded_images(
    ws: Any,
    *,
    image_col_idx: int = -1,
) -> Dict[int, Tuple[bytes, str]]:
    """Map 1-based Excel row number → (image bytes, extension) for pasted cell images."""
    out: Dict[int, Tuple[bytes, str]] = {}
    images = getattr(ws, '_images', None) or []
    for image in images:
        row, col = _image_anchor_row_col(getattr(image, 'anchor', None))
        if row is None or row <= 1:
            continue
        if image_col_idx >= 0 and col is not None and col != image_col_idx:
            continue
        try:
            data = image._data()
        except Exception:
            continue
        if not data:
            continue
        ext = _format_to_ext(
            str(getattr(image, 'format', '') or ''),
            str(getattr(image, 'path', '') or ''),
        )
        if row not in out:
            out[row] = (data, ext)
    return out


def _parse_xlsx_first_sheet(
    raw: bytes,
    max_rows: int,
) -> Tuple[List[Tuple[int, Dict[str, Any]]], Dict[int, Tuple[bytes, str]], Optional[str]]:
    """Parse first sheet rows and embedded cell images (row number is 1-based Excel row)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ([], {}, 'Excel import requires openpyxl (pip install openpyxl).')
    try:
        bio = io.BytesIO(raw)
        wb = load_workbook(bio, data_only=True)
        try:
            ws = wb.active
            rows_it = ws.iter_rows(values_only=True)
            first = next(rows_it, None)
            if first is None:
                return ([], {}, 'The worksheet is empty.')
            headers: List[str] = []
            for cell in first:
                if cell is None:
                    headers.append('')
                else:
                    text = str(cell).strip()
                    headers.append(text if text else '')
            image_col_idx = _header_image_col_index(headers)
            embedded = _extract_embedded_images(ws, image_col_idx=image_col_idx)
            out_rows: List[Tuple[int, Dict[str, Any]]] = []
            excel_row = 1
            for row in rows_it:
                excel_row += 1
                if len(out_rows) >= max_rows:
                    break
                rd: Dict[str, Any] = {}
                empty = True
                for i, header in enumerate(headers):
                    if not header:
                        continue
                    value = row[i] if i < len(row) else None
                    if value not in (None, ''):
                        empty = False
                    rd[header] = value
                if not empty or excel_row in embedded:
                    out_rows.append((excel_row, rd))
            return (out_rows, embedded, None)
        finally:
            try:
                wb.close()
            except Exception:
                pass
    except Exception as exc:
        return ([], {}, str(exc))


def _row_field(row: Dict[str, Any], *aliases: str) -> str:
    alias_keys = {_norm_key(alias) for alias in aliases}
    for header, value in row.items():
        if _norm_key(header) in alias_keys:
            return _cell_str(value)
    return ''


def _resolve_item(
    *,
    item_code_raw: str,
    barcode_raw: str,
    location_code: int,
) -> Tuple[Optional[int], str]:
    if item_code_raw:
        try:
            item_code = int(float(item_code_raw))
        except (TypeError, ValueError):
            return (None, 'Invalid ItemCode.')
        if item_code <= 0:
            return (None, 'ItemCode must be greater than zero.')
        item = get_item_by_code(item_code, location_code)
        if not item:
            return (None, f'Item {item_code} not found for location {location_code}.')
        return (item_code, '')

    barcode = barcode_raw.strip()
    if not barcode:
        return (None, 'ItemCode or Barcode is required.')

    item = get_item_by_manufacturer_id(barcode, location_code)
    if not item:
        item = get_item_by_alternate_barcode(barcode, location_code)
    if not item:
        return (None, f'No item found for barcode {barcode} at location {location_code}.')
    try:
        return (int(item.get('itemcode') or item.get('ITEMCODE')), '')
    except (TypeError, ValueError):
        return (None, f'Item for barcode {barcode} has invalid code.')


def _guess_ext_from_url(url: str, content_type: str = '') -> str:
    path = urlparse(url).path or ''
    ext = os.path.splitext(path)[1].lower()
    if ext in _ALLOWED_IMAGE_EXT:
        return ext
    ct = (content_type or '').split(';', 1)[0].strip().lower()
    mapping = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'image/gif': '.gif',
    }
    return mapping.get(ct, '.jpg')


def _save_item_image_bytes(data: bytes, ext: str, *, location_code: int, item_code: int) -> str:
    ext = ext.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise ValueError('Image must be PNG, JPG, JPEG, WEBP, or GIF.')
    if not data:
        raise ValueError('Image file is empty.')
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError('Image exceeds 8 MB limit.')
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    filename = f'item_{int(location_code)}_{int(item_code)}_{stamp}{ext}'
    target_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'itemmaster')
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, filename)
    with open(full_path, 'wb') as handle:
        handle.write(data)
    return f'uploads/itemmaster/{filename}'


def _normalize_image_url(url: str) -> str:
    cleaned = html.unescape(str(url or '').strip())
    if cleaned.startswith('//'):
        cleaned = f'https:{cleaned}'
    return cleaned


def _download_image(url: str) -> Tuple[bytes, str]:
    normalized = _normalize_image_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('ImageURL must start with http:// or https://')

    errors: List[str] = []
    header_sets = [
        {
            'User-Agent': _WEB_SEARCH_UA,
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': f'{parsed.scheme}://{parsed.netloc}/',
        },
        {
            'User-Agent': _WEB_SEARCH_UA,
            'Accept': 'image/*,*/*;q=0.8',
        },
    ]

    if requests:
        for headers in header_sets:
            try:
                resp = requests.get(
                    normalized,
                    headers=headers,
                    timeout=_DOWNLOAD_TIMEOUT_SEC,
                    allow_redirects=True,
                )
                if resp.status_code >= 400:
                    errors.append(f'HTTP {resp.status_code}')
                    continue
                data = resp.content[: _MAX_IMAGE_BYTES + 1]
                if len(data) > _MAX_IMAGE_BYTES:
                    raise ValueError('Downloaded image exceeds 8 MB limit.')
                if not data:
                    errors.append('empty response')
                    continue
                content_type = resp.headers.get('Content-Type', '')
                ext = _guess_ext_from_url(normalized, content_type)
                return (data, ext)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                continue

    req = Request(normalized, headers={'User-Agent': _WEB_SEARCH_UA})
    try:
        with urlopen(req, timeout=_DOWNLOAD_TIMEOUT_SEC) as resp:
            data = resp.read(_MAX_IMAGE_BYTES + 1)
            if len(data) > _MAX_IMAGE_BYTES:
                raise ValueError('Downloaded image exceeds 8 MB limit.')
            content_type = resp.headers.get('Content-Type', '')
    except URLError as exc:
        detail = '; '.join(errors[:2]) if errors else str(exc)
        raise ValueError(f'Could not download image: {detail}') from exc
    ext = _guess_ext_from_url(normalized, content_type)
    return (data, ext)


def _index_zip_images(raw: bytes) -> Tuple[Dict[str, Tuple[bytes, str]], Optional[str]]:
    if not raw:
        return ({}, None)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            indexed: Dict[str, Tuple[bytes, str]] = {}
            for name in archive.namelist():
                if name.endswith('/') or name.startswith('__MACOSX/'):
                    continue
                base = os.path.basename(name.replace('\\', '/'))
                if not base:
                    continue
                ext = os.path.splitext(base)[1].lower()
                if ext not in _ALLOWED_IMAGE_EXT:
                    continue
                data = archive.read(name)
                if len(data) > _MAX_IMAGE_BYTES:
                    return ({}, f'File {base} exceeds 8 MB limit inside ZIP.')
                indexed[base.lower()] = (data, ext)
            return (indexed, None)
    except zipfile.BadZipFile:
        return ({}, 'Images ZIP is not a valid zip file.')
    except Exception as exc:
        return ({}, str(exc))


def import_product_images_from_excel(
    excel_raw: bytes,
    *,
    default_location_code: Optional[int] = None,
    zip_raw: Optional[bytes] = None,
    download_urls: bool = True,
) -> Dict[str, Any]:
    """Import ITEMMASTER images from Excel rows (+ optional ZIP of local files)."""
    ensure_itemmaster_image_path_column()
    default_loc = int(default_location_code or resolve_location_code())

    if not excel_raw:
        return {'ok': False, 'error': 'Choose an Excel file (.xlsx).'}
    if len(excel_raw) > _MAX_EXCEL_BYTES:
        return {'ok': False, 'error': 'Excel file too large (max 50 MB).'}
    if zip_raw and len(zip_raw) > _MAX_ZIP_BYTES:
        return {'ok': False, 'error': 'Images ZIP too large (max 50 MB).'}

    rows, embedded_images, parse_err = _parse_xlsx_first_sheet(excel_raw, _MAX_ROWS)
    if parse_err:
        return {'ok': False, 'error': parse_err}
    if not rows:
        return {'ok': False, 'error': 'No data rows found in the Excel file.'}

    zip_index, zip_err = _index_zip_images(zip_raw or b'')
    if zip_err:
        return {'ok': False, 'error': zip_err}

    updated = 0
    failed = 0
    errors: List[str] = []

    for excel_row, row in rows:
        item_code_raw = _row_field(row, 'ItemCode', 'ITEMCODE', 'Code')
        barcode_raw = _row_field(row, 'Barcode', 'MANUFACTURERID', 'ManufacturerId')
        loc_raw = _row_field(row, 'LocationCode', 'LOCATIONCODE')
        image_url = _row_field(row, 'ImageURL', 'ImageUrl', 'URL')
        image_file = _row_field(row, 'ImageFileName', 'ImageFile', 'Filename', 'FileName')
        embedded = embedded_images.get(excel_row)

        try:
            loc = int(float(loc_raw)) if loc_raw else default_loc
        except (TypeError, ValueError):
            failed += 1
            errors.append(f'Row {excel_row}: invalid LocationCode.')
            continue

        item_code, item_err = _resolve_item(
            item_code_raw=item_code_raw,
            barcode_raw=barcode_raw,
            location_code=loc,
        )
        if item_err or item_code is None:
            failed += 1
            errors.append(f'Row {excel_row}: {item_err or "Item not found."}')
            continue

        if not embedded and not image_url and not image_file:
            failed += 1
            errors.append(
                f'Row {excel_row}: paste an image in the Image column, or provide ImageURL / ImageFileName.'
            )
            continue

        try:
            rel_path = ''
            if embedded:
                data, ext = embedded
                rel_path = _save_item_image_bytes(data, ext, location_code=loc, item_code=item_code)
            elif image_file:
                key = os.path.basename(image_file.replace('\\', '/')).lower()
                packed = zip_index.get(key)
                if not packed:
                    failed += 1
                    errors.append(f'Row {excel_row}: image file "{image_file}" not found in ZIP.')
                    continue
                data, ext = packed
                rel_path = _save_item_image_bytes(data, ext, location_code=loc, item_code=item_code)
            elif image_url:
                if download_urls:
                    data, ext = _download_image(image_url)
                    rel_path = _save_item_image_bytes(data, ext, location_code=loc, item_code=item_code)
                else:
                    rel_path = image_url[:500]

            ok, db_err = set_item_image_path(item_code, loc, rel_path or None)
            if not ok:
                failed += 1
                errors.append(f'Row {excel_row}: {db_err or "Could not save image path."}')
                continue
            updated += 1
        except ValueError as exc:
            failed += 1
            errors.append(f'Row {excel_row}: {exc}')
        except Exception as exc:
            failed += 1
            errors.append(f'Row {excel_row}: {exc}')

    processed = updated + failed
    ok = updated > 0 and failed == 0
    partial = updated > 0 and failed > 0
    summary = f'Processed {processed} row(s): {updated} updated'
    if failed:
        summary += f', {failed} failed'
    return {
        'ok': ok or partial,
        'partial': partial,
        'processed': processed,
        'updated': updated,
        'failed': failed,
        'errors': errors[:100],
        'error_count': len(errors),
        'message': summary,
        'location_code': default_loc,
    }


def _pick_first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in ('none', 'null', 'nan'):
            return text
    return ''


def _lookup_brand_name(item: Dict[str, Any]) -> str:
    name = _pick_first_text(item.get('brandname'), item.get('BRANDNAME'))
    if name:
        return name
    brand_code = item.get('brandcode') or item.get('BRANDCODE')
    if not brand_code:
        return ''
    try:
        rows = _safe_rows(
            "SELECT NAME FROM CATEGORY WHERE CODE = :code AND FLAG = 'B'",
            {'code': int(brand_code)},
        )
        if rows:
            return _pick_first_text(rows[0].get('name'), rows[0].get('NAME'))
    except Exception:
        pass
    return ''


def _normalize_barcode(raw: Any) -> str:
    digits = re.sub(r'\D', '', str(raw or ''))
    if len(digits) < 8:
        return ''
    return digits[:20]


def _fetch_openfoodfacts_image_by_barcode(barcode: str) -> Optional[str]:
    if not requests:
        return None
    headers = {'User-Agent': 'MamaHub-ProductImageFetch/1.0'}
    for path in (
        f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json',
        f'https://world.openfoodfacts.org/api/v2/product/{barcode}.json',
    ):
        try:
            resp = requests.get(path, headers=headers, timeout=(4, 10))
            if resp.status_code >= 400:
                continue
            data = resp.json() if resp.content else {}
            if int(data.get('status') or 0) != 1:
                continue
            product = data.get('product') or {}
            url = _pick_first_text(product.get('image_front_url'), product.get('image_url'))
            if url.startswith('http'):
                return url
        except Exception:
            continue
    return None


def _fetch_upcitemdb_image_by_barcode(barcode: str) -> Optional[str]:
    if not requests:
        return None
    try:
        resp = requests.get(
            'https://api.upcitemdb.com/prod/trial/lookup',
            params={'upc': barcode},
            headers={'Accept': 'application/json', 'User-Agent': 'MamaHub-ProductImageFetch/1.0'},
            timeout=(4, 10),
        )
        if resp.status_code >= 400:
            return None
        payload = resp.json() if resp.content else {}
        items = payload.get('items') if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            return None
        item = items[0] if isinstance(items[0], dict) else {}
        images = item.get('images')
        if isinstance(images, list) and images:
            url = _pick_first_text(images[0])
            if url.startswith('http'):
                return url
    except Exception:
        return None
    return None


def _search_openfoodfacts_image_by_name(query: str) -> Optional[str]:
    if not requests or not query.strip():
        return None
    try:
        resp = requests.get(
            'https://world.openfoodfacts.org/cgi/search.pl',
            params={
                'search_terms': query.strip()[:120],
                'search_simple': 1,
                'action': 'process',
                'json': 1,
                'page_size': 5,
            },
            headers={'User-Agent': 'MamaHub-ProductImageFetch/1.0'},
            timeout=(4, 12),
        )
        if resp.status_code >= 400:
            return None
        data = resp.json() if resp.content else {}
        products = data.get('products') if isinstance(data, dict) else None
        if not isinstance(products, list):
            return None
        for product in products:
            if not isinstance(product, dict):
                continue
            url = _pick_first_text(product.get('image_front_url'), product.get('image_url'))
            if url.startswith('http'):
                return url
    except Exception:
        return None
    return None


def _clean_search_text(text: str) -> str:
    cleaned = re.sub(r'[^\w\s\-\'"/#]+', ' ', str(text or ''), flags=re.UNICODE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:160]


def _dedupe_queries(queries: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for query in queries:
        key = query.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(query.strip())
    return out


def _build_image_search_queries(
    item_name: str,
    *,
    brand_name: str = '',
    category_name: str = '',
) -> List[str]:
    name = _clean_search_text(item_name)
    if not name:
        return []

    upper = name.upper()
    queries: List[str] = []
    number_match = re.search(r'\b(?:NUMBER|NO\.?|#)\s*(\d+)\b', upper)
    balloon_number = number_match.group(1) if number_match else None

    if 'BALLOON' in upper:
        if balloon_number:
            queries.append(f'foil balloon number {balloon_number} 16 inch party supplies product')
            queries.append(f'"number {balloon_number}" foil balloon birthday party decoration')
        queries.append(f'{name} foil balloon party product photo')
    elif any(token in upper for token in ('TOY', 'LEGO', 'DOLL', 'PUZZLE', 'GAME', 'SCOOTER', 'PLUSH')):
        queries.append(f'{name} toy product photo')
    else:
        queries.append(f'{name} product photo')

    if brand_name:
        brand = _clean_search_text(brand_name)
        if brand:
            queries.insert(0, f'{brand} {name} product photo')
    if category_name:
        category = _clean_search_text(category_name)
        if category and category.lower() not in name.lower():
            queries.append(f'{category} {name} product')

    return _dedupe_queries(queries)


def _score_image_url(url: str) -> int:
    lower = url.lower()
    if any(part in lower for part in _BAD_IMAGE_URL_PARTS):
        return -1
    for idx, host in enumerate(_PREFERRED_IMAGE_HOSTS):
        if host in lower:
            return 200 - idx
    if any(ext in lower for ext in ('.jpg', '.jpeg', '.png', '.webp')):
        return 80
    return 40


def _search_bing_image_urls(query: str, *, limit: int = 8) -> List[str]:
    if not requests or not query.strip():
        return []
    try:
        resp = requests.get(
            'https://www.bing.com/images/search',
            params={'q': query.strip()[:180], 'qft': '+filterui:photo-photo'},
            headers={'User-Agent': _WEB_SEARCH_UA},
            timeout=(4, 15),
        )
        if resp.status_code >= 400:
            return []
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)', resp.text)
        if not urls:
            urls = re.findall(r'"murl"\s*:\s*"(https?://[^"\\]+)"', resp.text)
        ranked: List[Tuple[int, str]] = []
        seen: set[str] = set()
        for raw_url in urls[:20]:
            url = _normalize_image_url(raw_url)
            key = url.lower()
            if not url.startswith('http') or key in seen:
                continue
            score = _score_image_url(url)
            if score < 0:
                continue
            seen.add(key)
            ranked.append((score, url))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [url for _, url in ranked[:limit]]
    except Exception:
        return []


def _search_bing_images(query: str) -> Optional[str]:
    urls = _search_bing_image_urls(query, limit=1)
    return urls[0] if urls else None


def _resolve_web_image_candidates(
    *,
    item_name: str,
    barcode: Any,
    brand_name: str = '',
    category_name: str = '',
) -> List[str]:
    """Return ordered unique image URLs to try for one product."""
    candidates: List[str] = []
    seen: set[str] = set()

    def _add(url: Optional[str]) -> None:
        if not url:
            return
        normalized = _normalize_image_url(url)
        key = normalized.lower()
        if normalized.startswith('http') and key not in seen:
            seen.add(key)
            candidates.append(normalized)

    for raw_code in (barcode,):
        code = _normalize_barcode(raw_code)
        if not code:
            continue
        _add(_fetch_openfoodfacts_image_by_barcode(code))
        time.sleep(0.2)
        _add(_fetch_upcitemdb_image_by_barcode(code))

    for query in _build_image_search_queries(
        item_name,
        brand_name=brand_name,
        category_name=category_name,
    ):
        for url in _search_bing_image_urls(query, limit=6):
            _add(url)
        time.sleep(0.15)

    food_query = item_name.strip()
    if brand_name and brand_name.upper() not in food_query.upper():
        food_query = f'{brand_name} {food_query}'.strip()
    if food_query:
        _add(_search_openfoodfacts_image_by_name(food_query))

    return candidates


def _resolve_web_image_url(
    *,
    item_name: str,
    barcode: Any,
    brand_name: str = '',
    category_name: str = '',
) -> Tuple[Optional[str], str]:
    """Return (image_url, source_label) from public product databases."""
    urls = _resolve_web_image_candidates(
        item_name=item_name,
        barcode=barcode,
        brand_name=brand_name,
        category_name=category_name,
    )
    if urls:
        return (urls[0], 'web-search')
    return (None, '')


def _list_items_missing_images(location_code: int, *, limit: int = 25) -> List[Dict[str, Any]]:
    ensure_itemmaster_image_path_column()
    lim = max(1, min(int(limit or 25), 100))
    rows = _safe_rows(
        """
        SELECT
            im.ITEMCODE AS item_code,
            im.ITEMNAME AS item_name,
            NVL(NULLIF(TRIM(im.MANUFACTURERID), ''), TRIM(im.RAWABICODE)) AS barcode,
            (
                SELECT NVL(MAX(brand.NAME), '')
                FROM CATEGORY brand
                WHERE brand.CODE = im.BRANDCODE AND brand.FLAG = 'B'
            ) AS brand_name,
            (
                SELECT NVL(MAX(cat.NAME), '')
                FROM CATEGORY cat
                WHERE cat.CODE = im.CATEGORYCODE AND cat.FLAG = 'C'
            ) AS category_name
        FROM ITEMMASTER im
        WHERE im.LOCATIONCODE = :loc
          AND (im.IMAGE_PATH IS NULL OR TRIM(im.IMAGE_PATH) = '')
        ORDER BY im.ITEMCODE DESC
        FETCH FIRST :lim ROWS ONLY
        """,
        {'loc': int(location_code), 'lim': lim},
    )
    return [dict(row) for row in rows]


def _public_image_url(image_path: Optional[str]) -> Optional[str]:
    raw = str(image_path or '').strip()
    if not raw:
        return None
    if raw.startswith(('http://', 'https://', 'data:', '/')):
        return raw
    return url_for('static', filename=raw)


def _try_fetch_web_image_for_item(
    *,
    item_code: int,
    item_name: str,
    barcode: Any,
    brand_name: str = '',
    category_name: str = '',
    location_code: int,
    download_images: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """Search the web and save the best image for one item. Returns (ok, message, image_path)."""
    image_urls = _resolve_web_image_candidates(
        item_name=item_name,
        barcode=barcode,
        brand_name=brand_name,
        category_name=category_name,
    )
    if not image_urls:
        return (False, 'No image found on the web.', None)

    last_error = ''
    for image_url in image_urls:
        try:
            rel_path = image_url[:500]
            if download_images:
                data, ext = _download_image(image_url)
                rel_path = _save_item_image_bytes(
                    data, ext, location_code=location_code, item_code=item_code
                )
            ok, db_err = set_item_image_path(item_code, location_code, rel_path)
            if not ok:
                last_error = db_err or 'Could not save image.'
                continue
            return (True, 'Image fetched and saved.', rel_path)
        except ValueError as exc:
            last_error = str(exc)
            continue
    return (False, last_error or 'Could not download any image candidate.', None)


def fetch_product_image_from_web(
    *,
    item_code: int,
    location_code: Optional[int] = None,
    download_images: bool = True,
) -> Dict[str, Any]:
    """Fetch and save a web image for one product by item code."""
    if not requests:
        return {
            'ok': False,
            'error': 'Web fetch requires the requests library (pip install requests).',
        }

    loc = int(location_code or resolve_location_code())
    ic = int(item_code)
    ensure_itemmaster_image_path_column()
    item = get_item_by_code(ic, loc)
    if not item:
        return {'ok': False, 'error': f'Item {ic} not found for location {loc}.'}

    item_name = _pick_first_text(item.get('itemname'), item.get('ITEMNAME'))
    barcode = _pick_first_text(
        item.get('manufacturerid'),
        item.get('MANUFACTURERID'),
        item.get('rawabicode'),
        item.get('RAWABICODE'),
    )
    category_name = _pick_first_text(item.get('categoryname'), item.get('CATEGORYNAME'))
    brand_name = _lookup_brand_name(item)

    ok, message, rel_path = _try_fetch_web_image_for_item(
        item_code=ic,
        item_name=item_name,
        barcode=barcode,
        brand_name=brand_name,
        category_name=category_name,
        location_code=loc,
        download_images=download_images,
    )
    if not ok:
        return {
            'ok': False,
            'error': message,
            'message': message,
            'item_code': ic,
            'location_code': loc,
        }
    return {
        'ok': True,
        'message': message,
        'item_code': ic,
        'location_code': loc,
        'image_path': rel_path,
        'image_url': _public_image_url(rel_path),
    }


def fetch_missing_product_images_from_web(
    *,
    location_code: Optional[int] = None,
    limit: int = 25,
    download_images: bool = True,
) -> Dict[str, Any]:
    """Find products without IMAGE_PATH and fetch image URLs from the web."""
    if not requests:
        return {
            'ok': False,
            'error': 'Web fetch requires the requests library (pip install requests).',
        }

    loc = int(location_code or resolve_location_code())
    candidates = _list_items_missing_images(loc, limit=limit)
    if not candidates:
        return {
            'ok': True,
            'processed': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'errors': [],
            'message': 'No products without images were found for this location.',
            'location_code': loc,
        }

    updated = 0
    skipped = 0
    failed = 0
    errors: List[str] = []

    for row in candidates:
        item_code = int(row.get('item_code') or row.get('ITEMCODE') or 0)
        item_name = _pick_first_text(row.get('item_name'), row.get('ITEMNAME'))
        barcode = row.get('barcode') or row.get('MANUFACTURERID')
        brand_name = _pick_first_text(row.get('brand_name'), row.get('BRANDNAME'))
        category_name = _pick_first_text(row.get('category_name'), row.get('CATEGORYNAME'))

        if item_code <= 0:
            skipped += 1
            continue

        try:
            ok, err_msg, rel_path = _try_fetch_web_image_for_item(
                item_code=item_code,
                item_name=item_name,
                barcode=barcode,
                brand_name=brand_name,
                category_name=category_name,
                location_code=loc,
                download_images=download_images,
            )
            if ok:
                updated += 1
                time.sleep(0.25)
            else:
                if 'no image found' in (err_msg or '').lower():
                    skipped += 1
                else:
                    failed += 1
                errors.append(f'Item {item_code}: {err_msg}')
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f'Item {item_code}: {exc}')

    processed = len(candidates)
    ok = updated > 0 and failed == 0
    partial = updated > 0 and (failed > 0 or skipped > 0)
    summary = f'Checked {processed} product(s): {updated} image(s) fetched'
    if skipped:
        summary += f', {skipped} not found on web'
    if failed:
        summary += f', {failed} failed'
    return {
        'ok': ok or partial,
        'partial': partial,
        'processed': processed,
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'errors': errors[:100],
        'error_count': len(errors),
        'message': summary,
        'location_code': loc,
    }
