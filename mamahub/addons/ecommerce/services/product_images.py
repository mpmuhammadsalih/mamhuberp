"""Bulk product image import for ecommerce Products (ITEMMASTER.IMAGE_PATH)."""
from __future__ import annotations

import html
import io
import json
import os
import re
import tempfile
import time
import zipfile
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from nexa_http import current_app, url_for

from addons.ecommerce.services.common import resolve_location_code
from db import (
    _get_connection,
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
_MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ZIP_LABEL = '2 GB'
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_PRODUCT_IMAGE_SIZE = 800
_MAX_FOLDER_IMAGES = 16
_DESC_TEXT_NAMES = {
    'description.txt',
    'description.md',
    'desc.txt',
    'details.txt',
}
_DESC_AR_TEXT_NAMES = {
    'description_ar.txt',
    'description-ar.txt',
    'description.ar.txt',
    'desc_ar.txt',
    'details_ar.txt',
    'description_arabic.txt',
}
_SPEC_TEXT_NAMES = {
    'specifications.txt',
    'specification.txt',
    'specs.txt',
    'features.txt',
}
_COPY_JSON_NAMES = {'product.json', 'details.json', 'info.json'}
_GENERIC_ZIP_FOLDERS = {
    'images',
    'image',
    'img',
    'imgs',
    'photos',
    'photo',
    'pics',
    'pictures',
    'gallery',
    'files',
    'file',
    'assets',
    'media',
    'pic',
    'fotos',
    'foto',
    'upload',
    'uploads',
    'export',
    'exports',
}
_ITEMMASTER_DESCRIPTION_MAX = 2000
_SPECS_MAX = 3500
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
_JOB_ID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
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


def safe_import_job_id(value: Any) -> str:
    job_id = str(value or '').strip().lower()
    return job_id if _JOB_ID_RE.match(job_id) else ''


def _progress_path(job_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f'mh-img-progress-{job_id}.json')


def write_import_progress(job_id: str, payload: Dict[str, Any]) -> None:
    job_id = safe_import_job_id(job_id)
    if not job_id:
        return
    path = _progress_path(job_id)
    tmp = path + '.tmp'
    body = dict(payload or {})
    body['job_id'] = job_id
    try:
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(body, handle, default=str)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def read_import_progress(job_id: str) -> Optional[Dict[str, Any]]:
    job_id = safe_import_job_id(job_id)
    if not job_id:
        return None
    path = _progress_path(job_id)
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clear_import_progress(job_id: str) -> None:
    job_id = safe_import_job_id(job_id)
    if not job_id:
        return
    path = _progress_path(job_id)
    try:
        os.unlink(path)
    except OSError:
        pass


def _emit_import_progress(
    progress_cb: Optional[Callable[[Dict[str, Any]], None]],
    **payload: Any,
) -> None:
    if not progress_cb:
        return
    try:
        progress_cb(payload)
    except Exception:
        pass


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

    barcode = _barcode_from_label(barcode_raw) or barcode_raw.strip()
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


def _normalize_item_image(data: bytes, ext: str) -> Tuple[bytes, str]:
    """Center-crop to a square and resize to 800×800 JPEG."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, ext
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            canvas = Image.new('RGB', img.size, (255, 255, 255))
            rgba = img.convert('RGBA')
            canvas.paste(rgba, mask=rgba.split()[-1])
            img = canvas
        else:
            img = img.convert('RGB')
        resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.LANCZOS)
        fitted = ImageOps.fit(img, (_PRODUCT_IMAGE_SIZE, _PRODUCT_IMAGE_SIZE), method=resample)
        out = io.BytesIO()
        fitted.save(out, format='JPEG', quality=88, optimize=True)
        result = out.getvalue()
        if not result or len(result) > _MAX_IMAGE_BYTES:
            return data, ext
        return result, '.jpg'
    except Exception:
        return data, ext


def _itemmaster_static_root() -> str:
    """ITEMMASTER upload root. Fall back when the request thread has no app context."""
    try:
        root = str(current_app.root_path or '').strip()
    except RuntimeError:
        root = ''
    if not root:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    return root


def _save_item_image_bytes(data: bytes, ext: str, *, location_code: int, item_code: int) -> str:
    ext = ext.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise ValueError('Image must be PNG, JPG, JPEG, WEBP, or GIF.')
    if not data:
        raise ValueError('Image file is empty.')
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValueError('Image exceeds 25 MB limit.')
    data, ext = _normalize_item_image(data, ext)
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError('Image exceeds 8 MB limit.')
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    filename = f'item_{int(location_code)}_{int(item_code)}_{stamp}{ext}'
    target_dir = os.path.join(_itemmaster_static_root(), 'static', 'uploads', 'itemmaster')
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


def _download_image(url: str, referer: str = '') -> Tuple[bytes, str]:
    normalized = _normalize_image_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('ImageURL must start with http:// or https://')

    errors: List[str] = []
    page_ref = str(referer or '').strip()
    header_sets = [
        {
            'User-Agent': _WEB_SEARCH_UA,
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': page_ref or f'{parsed.scheme}://{parsed.netloc}/',
        },
        {
            'User-Agent': _WEB_SEARCH_UA,
            'Accept': 'image/*,*/*;q=0.8',
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
                data = resp.content[: _MAX_DOWNLOAD_BYTES + 1]
                if len(data) > _MAX_DOWNLOAD_BYTES:
                    raise ValueError('Downloaded image exceeds 25 MB limit.')
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
            data = resp.read(_MAX_DOWNLOAD_BYTES + 1)
            if len(data) > _MAX_DOWNLOAD_BYTES:
                raise ValueError('Downloaded image exceeds 25 MB limit.')
            content_type = resp.headers.get('Content-Type', '')
    except URLError as exc:
        detail = '; '.join(errors[:2]) if errors else str(exc)
        raise ValueError(f'Could not download image: {detail}') from exc
    ext = _guess_ext_from_url(normalized, content_type)
    return (data, ext)


def _natural_sort_key(name: str) -> List[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', str(name or ''))]


def _barcode_folder_key(value: str) -> str:
    return re.sub(r'\s+', '', str(value or '').strip())


_BARCODE_NAME_RE = re.compile(r'^(\d{4,})(?:[-_.]+[A-Za-z0-9]+)?$')


def _barcode_from_label(value: str) -> str:
    """Accept 1200000001035, 1200000001035-1.jpg, or folder 1200000001035-1."""
    raw = os.path.splitext(os.path.basename(str(value or '').replace('\\', '/').strip()))[0]
    compact = _barcode_folder_key(raw)
    if not compact:
        return ''
    if compact.isdigit() and len(compact) >= 4:
        return compact
    match = _BARCODE_NAME_RE.match(compact)
    if match:
        return match.group(1)
    prefix = re.match(r'^(\d{4,})[-_.]', compact)
    return prefix.group(1) if prefix else ''


def _zip_path_parts(name: str) -> List[str]:
    return [part for part in str(name or '').replace('\\', '/').split('/') if part]


def _is_ignored_zip_name(name: str) -> bool:
    raw = str(name or '').replace('\\', '/')
    return (
        not raw
        or raw.endswith('/')
        or raw.startswith('__MACOSX/')
        or '/__MACOSX/' in raw
    )


def _looks_like_product_folder(value: str) -> bool:
    return bool(_barcode_from_label(value))


def _zip_common_root(names: List[str]) -> str:
    """Outer folder created when the user zips a parent directory."""
    useful: List[List[str]] = []
    for name in names:
        if _is_ignored_zip_name(name):
            continue
        parts = _zip_path_parts(name)
        if len(parts) >= 2:
            useful.append(parts)
    if not useful:
        return ''
    roots = {parts[0] for parts in useful}
    if len(roots) != 1:
        return ''
    root = next(iter(roots))
    if _looks_like_product_folder(root):
        return ''
    if all(len(parts) >= 3 for parts in useful):
        return root
    return ''


def safe_upload_relpath(name: str) -> str:
    """Keep a browser folder path; reject absolute paths and parent hops."""
    raw = str(name or '').replace('\\', '/').strip()
    if not raw or raw.startswith('/') or raw.startswith('../') or '/../' in raw:
        return ''
    parts = [part for part in raw.split('/') if part and part not in ('.', '..')]
    if not parts:
        return ''
    return '/'.join(parts)


def _product_folder_from_parts(parts: List[str], common_root: str = '') -> str:
    """Product folder, ignoring a ZIP wrapper and generic image subfolders."""
    dirs = [part for part in parts[:-1] if part and not str(part).startswith('.')]
    if not dirs:
        return ''
    if common_root and _barcode_folder_key(dirs[0]) == _barcode_folder_key(common_root):
        dirs = dirs[1:]
    while dirs and str(dirs[-1]).strip().lower() in _GENERIC_ZIP_FOLDERS:
        dirs = dirs[:-1]
    if not dirs:
        return ''
    folder = _barcode_folder_key(dirs[-1])
    if not folder or folder.startswith('.'):
        return ''
    return _barcode_from_label(folder) or folder


def _product_key_from_parts(parts: List[str], common_root: str = '') -> str:
    """Barcode from a folder, or from a file named 1200000001035-1.jpg."""
    if len(parts) >= 2:
        folder = _product_folder_from_parts(parts, common_root)
        if folder:
            return _barcode_from_label(folder) or folder
    if parts:
        return _barcode_from_label(parts[-1])
    return ''


def _folder_lookup_keys(value: str) -> List[str]:
    raw = str(value or '').strip().replace('\\', '/')
    if not raw:
        return []
    base = raw.rstrip('/').split('/')[-1]
    keys: List[str] = []
    for candidate in (raw, base):
        compact = _barcode_folder_key(candidate)
        if compact:
            keys.append(compact)
        extracted = _barcode_from_label(candidate)
        if extracted:
            keys.append(extracted)
        lowered = str(candidate or '').strip().lower()
        if lowered:
            keys.append(lowered)
    seen = set()
    unique: List[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def _lookup_zip_folder_files(
    zip_folders: Optional[Dict[str, List[Tuple[bytes, str]]]],
    *names: Any,
) -> Optional[List[Tuple[bytes, str]]]:
    if not zip_folders:
        return None
    by_lower = {str(key).lower(): files for key, files in zip_folders.items()}
    for name in names:
        for key in _folder_lookup_keys(str(name or '')):
            if key in zip_folders and zip_folders[key]:
                return zip_folders[key]
            found = by_lower.get(key.lower())
            if found:
                return found
    return None


def _decode_zip_text(raw: bytes) -> str:
    if not raw:
        return ''
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace').strip()


def _item_existing_image_path(item_code: int, location_code: int) -> str:
    item = get_item_by_code(int(item_code), int(location_code)) or {}
    return str(item.get('image_path') or item.get('IMAGE_PATH') or '').strip()


def _folder_copy_parts(
    texts: Optional[Dict[str, Tuple[str, ...]]],
    folder: str,
) -> Tuple[str, str, str]:
    raw = (texts or {}).get(folder) or ('', '', '')
    desc = str(raw[0] if len(raw) > 0 else '') or ''
    specs = str(raw[1] if len(raw) > 1 else '') or ''
    desc_ar = str(raw[2] if len(raw) > 2 else '') or ''
    return (desc, specs, desc_ar)


def _apply_imported_product_text(
    item_code: int,
    *,
    location_code: int,
    description: str = '',
    specifications: str = '',
    description_ar: str = '',
) -> Tuple[bool, bool, str]:
    """Save imported description, Arabic description, and specifications."""
    from addons.ecommerce.services import product_edit as product_edit_svc
    from addons.ecommerce.services import product_web_meta as web_meta_svc

    desc = str(description or '').strip()
    specs = str(specifications or '').strip()
    desc_ar = str(description_ar or '').strip()
    if desc:
        desc = ' '.join(desc.split())[:_ITEMMASTER_DESCRIPTION_MAX]
    if specs:
        specs = specs[:_SPECS_MAX]
    if desc_ar:
        desc_ar = desc_ar[:3500]
    if not desc and not specs and not desc_ar:
        return (False, False, '')
    if desc:
        ok, err = product_edit_svc.set_item_description_text(
            int(item_code),
            desc,
            location_code=int(location_code),
        )
        if not ok:
            return (False, False, err or 'Could not save description.')
    meta_kwargs: Dict[str, Any] = {}
    if specs:
        meta_kwargs['specifications'] = specs
        meta_kwargs['touch_specs'] = True
    if desc_ar:
        meta_kwargs['description_ar'] = desc_ar
        meta_kwargs['touch_description_ar'] = True
    if meta_kwargs:
        ok, err = web_meta_svc.save_product_web_meta(int(item_code), **meta_kwargs)
        if not ok:
            return (bool(desc), False, err or 'Could not save product text.')
    return (bool(desc or desc_ar), bool(specs), '')


def _zip_folder_copy_texts(archive: zipfile.ZipFile) -> Dict[str, Tuple[str, str, str]]:
    """Map folder -> (description, specifications, description_ar) from text/JSON files."""
    texts: Dict[str, Tuple[str, str, str]] = {}
    names = archive.namelist()
    common_root = _zip_common_root(names)
    for name in names:
        if _is_ignored_zip_name(name):
            continue
        parts = _zip_path_parts(name)
        if not parts:
            continue
        folder = _product_key_from_parts(parts, common_root)
        if not folder:
            continue
        base = parts[-1].lower()
        try:
            raw = archive.read(name)
        except Exception:
            continue
        desc, specs, desc_ar = _folder_copy_parts(texts, folder)
        if base in _COPY_JSON_NAMES:
            try:
                payload = json.loads(_decode_zip_text(raw) or '{}')
            except ValueError:
                payload = {}
            if isinstance(payload, dict):
                raw_desc = payload.get('description') or payload.get('Description') or ''
                raw_desc_ar = (
                    payload.get('description_ar')
                    or payload.get('DescriptionAr')
                    or payload.get('descriptionArabic')
                    or payload.get('arabic_description')
                    or ''
                )
                raw_specs = (
                    payload.get('specifications')
                    or payload.get('specification')
                    or payload.get('features')
                    or ''
                )
                if isinstance(raw_desc, list):
                    raw_desc = '\n'.join(str(part).strip() for part in raw_desc if str(part).strip())
                if isinstance(raw_desc_ar, list):
                    raw_desc_ar = '\n'.join(
                        str(part).strip() for part in raw_desc_ar if str(part).strip()
                    )
                if isinstance(raw_specs, list):
                    raw_specs = '\n'.join(str(part).strip() for part in raw_specs if str(part).strip())
                desc = desc or str(raw_desc).strip()
                desc_ar = desc_ar or str(raw_desc_ar).strip()
                specs = specs or str(raw_specs).strip()
        elif base in _DESC_AR_TEXT_NAMES:
            desc_ar = _decode_zip_text(raw)
        elif base in _DESC_TEXT_NAMES:
            desc = _decode_zip_text(raw)
        elif base in _SPEC_TEXT_NAMES:
            specs = _decode_zip_text(raw)
        if desc or specs or desc_ar:
            texts[folder] = (desc, specs, desc_ar)
    return texts


def _index_zip_barcode_folders(
    raw: bytes,
) -> Tuple[Dict[str, List[Tuple[bytes, str]]], Optional[str]]:
    """Map barcode folder name -> images, sorted by file name."""
    if not raw:
        return ({}, None)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            common_root = _zip_common_root(names)
            grouped: Dict[str, List[Tuple[str, bytes, str]]] = {}
            for name in names:
                if _is_ignored_zip_name(name):
                    continue
                parts = _zip_path_parts(name)
                if not parts:
                    continue
                folder = _product_key_from_parts(parts, common_root)
                if not folder:
                    continue
                base = parts[-1]
                ext = os.path.splitext(base)[1].lower()
                if ext not in _ALLOWED_IMAGE_EXT:
                    continue
                data = archive.read(name)
                if len(data) > _MAX_IMAGE_BYTES:
                    return ({}, f'File {base} in folder {folder} exceeds 8 MB limit.')
                if not data:
                    continue
                grouped.setdefault(folder, []).append((base, data, ext))
            folders: Dict[str, List[Tuple[bytes, str]]] = {}
            for folder, files in grouped.items():
                files.sort(key=lambda item: _natural_sort_key(item[0]))
                packed = [(data, ext) for _name, data, ext in files[:_MAX_FOLDER_IMAGES]]
                folders[folder] = packed
                lowered = str(folder).lower()
                if lowered not in folders:
                    folders[lowered] = packed
            return (folders, None)
    except zipfile.BadZipFile:
        return ({}, 'Images ZIP is not a valid zip file.')
    except Exception as exc:
        return ({}, str(exc))


def _clear_product_gallery(item_code: int) -> None:
    from addons.ecommerce import media_db
    from addons.ecommerce.services import media as media_svc

    if not media_db.media_table_ready():
        return
    rows, _ = media_db.list_media(placement='product', active_only=False)
    prefix = '/media/files/'
    for row in rows:
        if str(row.get('ref_key') or '').strip() != str(item_code):
            continue
        media_id = int(row.get('media_id') or 0)
        if media_id and row.get('is_active'):
            media_db.deactivate_media(media_id)
        raw = str(row.get('image_url') or '').strip()
        if raw.startswith(prefix):
            filename = raw[len(prefix) :].split('?', 1)[0]
            path = media_svc.uploads_dir() / filename
            try:
                if path.is_file() and '/' not in filename and '..' not in filename:
                    path.unlink()
            except OSError:
                pass


def _delete_item_local_files(
    location_code: int,
    item_code: int,
    *,
    keep_name: str = '',
) -> None:
    """Delete leftover Item Master files for this SKU, optionally keeping one new file."""
    target_dir = os.path.join(_itemmaster_static_root(), 'static', 'uploads', 'itemmaster')
    prefix = f'item_{int(location_code)}_{int(item_code)}_'
    keep = os.path.basename(str(keep_name or '').strip())
    if not os.path.isdir(target_dir):
        return
    try:
        names = os.listdir(target_dir)
    except OSError:
        return
    for name in names:
        if not name.startswith(prefix) or name == keep:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _ALLOWED_IMAGE_EXT:
            continue
        full = os.path.join(target_dir, name)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except OSError:
            continue


def _replace_existing_item_images(
    item_code: int,
    location_code: int,
    *,
    keep_rel_path: str = '',
    previous_path: str = '',
) -> None:
    """Remove the previous main photo, leftover SKU files, and gallery before/after replace."""
    if previous_path and previous_path != keep_rel_path:
        _delete_local_image(previous_path)
    _delete_item_local_files(
        location_code,
        item_code,
        keep_name=os.path.basename(str(keep_rel_path or '').strip()),
    )
    _clear_product_gallery(int(item_code))


def _add_product_gallery_image(item_code: int, image_url: str, sort_order: int) -> bool:
    from addons.ecommerce import media_db

    if not media_db.media_table_ready():
        return False
    ok, _msg, row = media_db.upsert_media(
        {
            'placement': 'product',
            'ref_key': str(item_code),
            'title': f'Product {item_code} gallery',
            'subtitle': None,
            'image_url': image_url,
            'link_url': None,
            'alt_text': f'Product {item_code} photo',
            'sort_order': sort_order,
            'is_active': True,
            'meta': {},
        }
    )
    return bool(ok and row)


def _save_item_images_from_files(
    item_code: int,
    location_code: int,
    files: List[Tuple[bytes, str]],
    *,
    replace_existing: bool = False,
) -> Tuple[bool, str, int]:
    if not files:
        return (False, 'No images in folder.', 0)
    existing = _item_existing_image_path(item_code, location_code)
    if existing and not replace_existing:
        return (True, '', 0)
    if replace_existing:
        _clear_product_gallery(int(item_code))
    first_data, first_ext = files[0]
    rel_path = _save_item_image_bytes(
        first_data, first_ext, location_code=location_code, item_code=item_code
    )
    ok, db_err = set_item_image_path(int(item_code), int(location_code), rel_path)
    if not ok:
        return (False, db_err or 'Could not save main image.', 0)
    _replace_existing_item_images(
        int(item_code),
        int(location_code),
        keep_rel_path=rel_path,
        previous_path=existing,
    )
    gallery = 0
    if len(files) > 1:
        from addons.ecommerce.services import media as media_svc

        for data, ext in files[1:]:
            data, ext = _normalize_item_image(data, ext)
            saved, _msg, path = media_svc.save_bytes(data, ext, stem=f'product-{item_code}')
            if saved and path and _add_product_gallery_image(int(item_code), path, gallery):
                gallery += 1
    return (True, '', gallery)


def _zip_folder_member_names(archive: zipfile.ZipFile) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    names = archive.namelist()
    common_root = _zip_common_root(names)
    for name in names:
        if _is_ignored_zip_name(name):
            continue
        parts = _zip_path_parts(name)
        if not parts:
            continue
        folder = _product_key_from_parts(parts, common_root)
        if not folder:
            continue
        base = parts[-1]
        ext = os.path.splitext(base)[1].lower()
        if ext not in _ALLOWED_IMAGE_EXT:
            continue
        grouped.setdefault(folder, []).append(name)
    for folder, names in grouped.items():
        names.sort(key=lambda n: _natural_sort_key(os.path.basename(n.replace('\\', '/'))))
        grouped[folder] = names[:_MAX_FOLDER_IMAGES]
    return grouped


def _read_zip_member_images(
    archive: zipfile.ZipFile,
    names: List[str],
) -> Tuple[List[Tuple[bytes, str]], Optional[str]]:
    files: List[Tuple[bytes, str]] = []
    for name in names:
        base = os.path.basename(name.replace('\\', '/'))
        ext = os.path.splitext(base)[1].lower()
        data = archive.read(name)
        if len(data) > _MAX_IMAGE_BYTES:
            return ([], f'File {base} exceeds 8 MB limit.')
        if data:
            files.append((data, ext))
    return (files, None)


def _import_barcode_folder_images(
    folders: Dict[str, List[Tuple[bytes, str]]],
    default_loc: int,
    texts: Optional[Dict[str, Tuple[str, ...]]] = None,
    *,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    updated = 0
    failed = 0
    kept = 0
    gallery_total = 0
    copy_total = 0
    errors: List[str] = []
    folder_texts = texts or {}
    for barcode, files in folders.items():
        item_code, item_err = _resolve_item(
            item_code_raw='',
            barcode_raw=barcode,
            location_code=default_loc,
        )
        if item_err or item_code is None:
            try:
                maybe_code = int(barcode)
            except (TypeError, ValueError):
                maybe_code = 0
            if maybe_code > 0:
                item_code, item_err = _resolve_item(
                    item_code_raw=str(maybe_code),
                    barcode_raw='',
                    location_code=default_loc,
                )
        if item_err or item_code is None:
            failed += 1
            errors.append(f'Folder {barcode}: {item_err or "barcode not found."}')
            continue
        desc, specs, desc_ar = _folder_copy_parts(folder_texts, barcode)
        try:
            saved_images = False
            skip_images = bool(files) and (not replace_existing) and bool(
                _item_existing_image_path(item_code, default_loc)
            )
            gallery = 0
            if files and skip_images:
                kept += 1
            elif files:
                ok, err, gallery = _save_item_images_from_files(
                    item_code,
                    default_loc,
                    files,
                    replace_existing=replace_existing,
                )
                if not ok:
                    failed += 1
                    errors.append(f'Folder {barcode}: {err}')
                    continue
                saved_images = True
                gallery_total += gallery
            elif not desc and not specs and not desc_ar:
                failed += 1
                errors.append(f'Folder {barcode}: No images in folder.')
                continue
            if desc or specs or desc_ar:
                _d_ok, _s_ok, copy_err = _apply_imported_product_text(
                    item_code,
                    location_code=default_loc,
                    description=desc,
                    specifications=specs,
                    description_ar=desc_ar,
                )
                if copy_err:
                    errors.append(f'Folder {barcode}: {copy_err}')
                else:
                    copy_total += 1
            if saved_images or skip_images or desc or specs or desc_ar:
                updated += 1
        except ValueError as exc:
            failed += 1
            errors.append(f'Folder {barcode}: {exc}')
        except Exception as exc:
            failed += 1
            errors.append(f'Folder {barcode}: {exc}')

    processed = updated + failed
    ok = updated > 0 and failed == 0
    partial = updated > 0 and failed > 0
    summary = f'Processed {processed} folder(s): {updated} product(s) updated'
    if kept:
        summary += f', {kept} existing image(s) kept'
    if gallery_total:
        summary += f', {gallery_total} extra gallery photo(s)'
    if copy_total:
        summary += f', {copy_total} description/specification update(s)'
    if failed:
        summary += f', {failed} failed'
    return {
        'ok': ok or partial,
        'partial': partial,
        'processed': processed,
        'updated': updated,
        'failed': failed,
        'kept': kept,
        'errors': errors[:100],
        'error_count': len(errors),
        'gallery_total': gallery_total,
        'copy_total': copy_total,
        'message': summary,
        'location_code': default_loc,
    }


def _group_uploaded_folder_images(
    uploads: List[Tuple[str, bytes]],
) -> Tuple[Dict[str, List[Tuple[bytes, str]]], List[str]]:
    """Group uploaded files by barcode folder name. Images only."""
    names = [path for path, _data in uploads]
    common_root = _zip_common_root(names)
    grouped: Dict[str, List[Tuple[str, bytes, str]]] = {}
    errors: List[str] = []
    for path, data in uploads:
        safe = safe_upload_relpath(path)
        if not safe or _is_ignored_zip_name(safe):
            continue
        parts = _zip_path_parts(safe)
        if not parts:
            continue
        base = parts[-1]
        ext = os.path.splitext(base)[1].lower()
        if ext not in _ALLOWED_IMAGE_EXT:
            continue
        if len(data) > _MAX_IMAGE_BYTES:
            errors.append(f'File {base} exceeds 8 MB limit.')
            continue
        folder = _product_key_from_parts(parts, common_root)
        if not folder:
            continue
        grouped.setdefault(folder, []).append((base, data, ext))
    result: Dict[str, List[Tuple[bytes, str]]] = {}
    for folder, items in grouped.items():
        items.sort(key=lambda item: _natural_sort_key(item[0]))
        result[folder] = [(data, ext) for _name, data, ext in items[:_MAX_FOLDER_IMAGES]]
    return (result, errors)


def import_product_images_from_folder_uploads(
    uploads: List[Tuple[str, bytes]],
    *,
    default_location_code: Optional[int] = None,
    replace_existing: bool = False,
    only_item_code: Optional[int] = None,
    fallback_barcode: str = '',
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Import images only from barcode-named folders. Skips products that already have an image unless replace_existing."""
    ensure_itemmaster_image_path_column()
    default_loc = int(default_location_code or resolve_location_code())
    if not uploads:
        return {'ok': False, 'error': 'Choose a folder of images. Folder name must be the barcode.'}

    folders, read_errors = _group_uploaded_folder_images(uploads)
    if only_item_code and not folders:
        loose: List[Tuple[bytes, str]] = []
        for path, data in uploads:
            safe = safe_upload_relpath(path)
            ext = os.path.splitext(os.path.basename(safe))[1].lower()
            if ext in _ALLOWED_IMAGE_EXT and data:
                if len(data) > _MAX_IMAGE_BYTES:
                    read_errors.append(f'File {os.path.basename(safe)} exceeds 8 MB limit.')
                    continue
                loose.append((data, ext))
        if loose:
            key = _barcode_folder_key(fallback_barcode) or str(int(only_item_code))
            folders = {key: loose[:_MAX_FOLDER_IMAGES]}

    if only_item_code and folders:
        kept: Dict[str, List[Tuple[bytes, str]]] = {}
        for barcode, files in folders.items():
            item_code, _err = _resolve_item(
                item_code_raw='',
                barcode_raw=barcode,
                location_code=default_loc,
            )
            if item_code is None:
                try:
                    maybe_code = int(barcode)
                except (TypeError, ValueError):
                    maybe_code = 0
                if maybe_code > 0:
                    item_code, _err = _resolve_item(
                        item_code_raw=str(maybe_code),
                        barcode_raw='',
                        location_code=default_loc,
                    )
            if item_code == int(only_item_code):
                kept[barcode] = files
        want = _barcode_from_label(fallback_barcode) or _barcode_folder_key(fallback_barcode)
        if not kept and want and want in folders:
            kept[want] = folders[want]
        if not kept and len(folders) == 1:
            barcode, files = next(iter(folders.items()))
            return {
                'ok': False,
                'error': (
                    f'Folder {barcode} is not this product barcode'
                    + (f' ({fallback_barcode}).' if fallback_barcode else '.')
                ),
            }
        folders = kept

    if not folders:
        return {
            'ok': False,
            'error': (
                'No barcode folders found. Put images in a folder named with the barcode, '
                'for example 1200000001035/1.jpg.'
            ),
        }

    _emit_import_progress(
        progress_cb,
        phase='importing',
        total=len(folders),
        processed=0,
        updated=0,
        failed=0,
        current='',
        done=False,
    )
    result = _import_barcode_folder_images(
        folders,
        default_loc,
        texts=None,
        replace_existing=replace_existing,
    )
    if read_errors:
        errors = list(result.get('errors') or [])
        errors.extend(read_errors[:20])
        result['errors'] = errors[:100]
        result['error_count'] = len(result['errors'])
        if read_errors and not result.get('updated'):
            result['ok'] = False
            result['error'] = read_errors[0]
    _emit_import_progress(
        progress_cb,
        phase='done',
        total=len(folders),
        processed=int(result.get('processed') or 0),
        updated=int(result.get('updated') or 0),
        failed=int(result.get('failed') or 0),
        current='',
        done=True,
        message=str(result.get('message') or ''),
        ok=bool(result.get('ok')),
    )
    return result


_DRIVE_HOSTS = ('drive.google.com', 'docs.google.com', 'drive.usercontent.google.com')
_DRIVE_FILE_RE = re.compile(r'/file/d/([A-Za-z0-9_-]+)')
_DRIVE_FOLDER_RE = re.compile(r'/folders/([A-Za-z0-9_-]+)')
_DRIVE_OPEN_ID_RE = re.compile(r'[?&]id=([A-Za-z0-9_-]+)')
_DRIVE_CONFIRM_RE = re.compile(r'confirm=([0-9A-Za-z_-]+)')
_DRIVE_CONFIRM_INPUT_RE = re.compile(r'name=["\']confirm["\']\s+value=["\']([^"\']+)["\']', re.I)
_DRIVE_MAX_FILES = 300
_DRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder'


def _drive_api_key() -> str:
    return str(os.environ.get('GOOGLE_DRIVE_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip()


def parse_google_drive_link(url: str) -> Tuple[str, str]:
    """Return ('folder'|'file'|'', id) from a Google Drive share link."""
    raw = _normalize_image_url(url)
    parsed = urlparse(raw)
    host = (parsed.hostname or '').lower()
    if host not in _DRIVE_HOSTS and not host.endswith('.google.com'):
        return ('', '')
    path = parsed.path or ''
    folder = _DRIVE_FOLDER_RE.search(path)
    if folder:
        return ('folder', folder.group(1))
    file_id = _DRIVE_FILE_RE.search(path)
    if file_id:
        return ('file', file_id.group(1))
    params = parse_qs(parsed.query or '')
    raw_id = str((params.get('id') or [''])[0]).strip()
    if not raw_id:
        match = _DRIVE_OPEN_ID_RE.search(raw)
        raw_id = match.group(1) if match else ''
    if not raw_id:
        return ('', '')
    if 'folders' in path:
        return ('folder', raw_id)
    return ('file', raw_id)


def _drive_headers() -> Dict[str, str]:
    return {
        'User-Agent': _WEB_SEARCH_UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }


def _drive_get(url: str, *, stream: bool = False):
    if not requests:
        raise ValueError('Google Drive import needs the requests library.')
    return requests.get(
        url,
        headers=_drive_headers(),
        timeout=_DOWNLOAD_TIMEOUT_SEC,
        allow_redirects=True,
        stream=stream,
    )


def _list_drive_folder_api(folder_id: str) -> List[Dict[str, str]]:
    key = _drive_api_key()
    if not key:
        return []
    items: List[Dict[str, str]] = []
    page = ''
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        params = {
            'q': query,
            'fields': 'nextPageToken,files(id,name,mimeType)',
            'pageSize': 200,
            'key': key,
            'supportsAllDrives': 'true',
            'includeItemsFromAllDrives': 'true',
        }
        if page:
            params['pageToken'] = page
        resp = _drive_get('https://www.googleapis.com/drive/v3/files?' + urlencode(params))
        if resp.status_code >= 400:
            break
        payload = resp.json() if resp.content else {}
        for row in payload.get('files') or []:
            items.append({
                'id': str(row.get('id') or ''),
                'name': str(row.get('name') or ''),
                'mimeType': str(row.get('mimeType') or ''),
            })
        page = str(payload.get('nextPageToken') or '')
        if not page or len(items) >= _DRIVE_MAX_FILES:
            break
    return items


def _drive_folder_label(folder_id: str, body: str = '') -> str:
    title = ''
    match = re.search(r'<title>([^<]+)</title>', body or '', re.I)
    if match:
        title = html.unescape(match.group(1)).strip()
        title = re.sub(r'\s*[-–|]\s*Google Drive.*$', '', title, flags=re.I).strip()
    key = _barcode_from_label(title) or (_barcode_folder_key(title) if _looks_like_product_folder(title) else '')
    if key:
        return key
    return _barcode_from_label(folder_id) or ''


def _list_drive_folder_html(folder_id: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen = set()
    pages = [
        f'https://drive.google.com/embeddedfolderview?id={folder_id}#list',
        f'https://drive.google.com/embeddedfolderview?id={folder_id}#grid',
        f'https://drive.google.com/drive/folders/{folder_id}?usp=sharing',
    ]
    entry_re = re.compile(
        r'id=["\']entry-([A-Za-z0-9_-]+)["\'][\s\S]{0,2400}?'
        r'(?:flip-entry-title[^>]*>([^<]+)|aria-label=["\']([^"\']+)["\']|'
        r'title=["\']([^"\']+)["\'])',
        re.I,
    )
    file_href = re.compile(
        r'href=["\']https?://drive\.google\.com/file/d/([A-Za-z0-9_-]+)',
        re.I,
    )
    title_re = re.compile(r'flip-entry-title[^>]*>([^<]+)', re.I)
    id_name = re.compile(
        r'\["(?P<name>[^"]+\.(?:jpe?g|png|webp|gif))",\s*"'
        r'(?:image/[^"]+|application/octet-stream)"[\s\S]{0,240}?'
        r'"(?P<id>[A-Za-z0-9_-]{20,})"',
        re.I,
    )
    folder_label = ''

    def add_item(file_id: str, name: str, mime: str) -> None:
        file_id = str(file_id or '').strip()
        if not file_id or file_id in seen or file_id == folder_id:
            return
        seen.add(file_id)
        clean = html.unescape(str(name or '')).strip() or f'drive-{file_id[:8]}'
        items.append({'id': file_id, 'name': clean, 'mimeType': mime})

    for page_url in pages:
        try:
            resp = _drive_get(page_url)
        except Exception:
            continue
        if resp.status_code >= 400 or not resp.text:
            continue
        body = resp.text
        if not folder_label:
            folder_label = _drive_folder_label(folder_id, body)
        for match in entry_re.finditer(body):
            name = match.group(2) or match.group(3) or match.group(4) or ''
            mime = _DRIVE_FOLDER_MIME if not os.path.splitext(name)[1] else 'image/*'
            add_item(match.group(1), name, mime)
        titles = [html.unescape(m.group(1)).strip() for m in title_re.finditer(body)]
        file_ids = [m.group(1) for m in file_href.finditer(body)]
        for index, file_id in enumerate(file_ids):
            name = titles[index] if index < len(titles) else ''
            add_item(file_id, name, 'image/*')
        for match in id_name.finditer(body):
            add_item(match.group('id'), match.group('name'), 'image/*')
        if items:
            break
    if folder_label:
        for row in items:
            name = str(row.get('name') or '')
            if row.get('mimeType') == _DRIVE_FOLDER_MIME:
                continue
            if not _barcode_from_label(name):
                base = os.path.basename(name) or name
                row['name'] = f'{folder_label}/{base}'
    return items


def _list_drive_folder(folder_id: str, *, depth: int = 0) -> List[Dict[str, str]]:
    rows = _list_drive_folder_api(folder_id) or _list_drive_folder_html(folder_id)
    if depth >= 2:
        return rows
    expanded: List[Dict[str, str]] = []
    for row in rows:
        if row.get('mimeType') == _DRIVE_FOLDER_MIME and row.get('id'):
            prefix = str(row.get('name') or '').strip()
            for child in _list_drive_folder(row['id'], depth=depth + 1):
                child_name = str(child.get('name') or '')
                if prefix and '/' not in child_name:
                    child = dict(child)
                    child['name'] = f'{prefix}/{child_name}'
                expanded.append(child)
        else:
            expanded.append(row)
    return expanded[:_DRIVE_MAX_FILES]


def _download_drive_file(file_id: str, filename: str = '') -> Tuple[bytes, str]:
    if not requests:
        raise ValueError('Google Drive import needs the requests library.')
    session = requests.Session()
    session.headers.update(_drive_headers())
    urls = [
        f'https://drive.google.com/uc?export=download&id={file_id}',
        f'https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t',
    ]
    last_error = 'Could not download Google Drive file.'
    for url in urls:
        resp = session.get(url, timeout=_DOWNLOAD_TIMEOUT_SEC, allow_redirects=True)
        content_type = str(resp.headers.get('Content-Type') or '').lower()
        data = resp.content or b''
        if resp.status_code >= 400:
            last_error = f'HTTP {resp.status_code}'
            continue
        if data and 'text/html' in content_type:
            token_match = _DRIVE_CONFIRM_RE.search(resp.text) or _DRIVE_CONFIRM_INPUT_RE.search(resp.text)
            if token_match:
                confirm_url = f'https://drive.google.com/uc?export=download&id={file_id}&confirm={token_match.group(1)}'
                resp = session.get(confirm_url, timeout=_DOWNLOAD_TIMEOUT_SEC, allow_redirects=True)
                content_type = str(resp.headers.get('Content-Type') or '').lower()
                data = resp.content or b''
        if not data:
            last_error = 'empty file'
            continue
        if 'text/html' in content_type and data[:15].lower().find(b'<html') != -1:
            last_error = 'Drive file is not public. Set sharing to Anyone with the link.'
            continue
        if len(data) > _MAX_DOWNLOAD_BYTES:
            raise ValueError('Downloaded image exceeds 25 MB limit.')
        ext = _guess_ext_from_url(filename or url, content_type)
        if ext not in _ALLOWED_IMAGE_EXT:
            ext = _guess_ext_from_url(filename, '') or '.jpg'
        return (data, ext)
    raise ValueError(last_error)


def import_product_images_from_drive_url(
    drive_url: str,
    *,
    default_location_code: Optional[int] = None,
    replace_existing: bool = False,
    only_item_code: Optional[int] = None,
    fallback_barcode: str = '',
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Fetch images from a public Google Drive file or folder. Skips SKUs that already have a photo."""
    kind, drive_id = parse_google_drive_link(drive_url)
    if not drive_id:
        return {'ok': False, 'error': 'Paste a Google Drive file or folder link.'}

    _emit_import_progress(
        progress_cb,
        phase='preparing',
        total=0,
        processed=0,
        updated=0,
        failed=0,
        current='Reading Google Drive…',
        done=False,
    )
    uploads: List[Tuple[str, bytes]] = []
    try:
        if kind == 'folder':
            entries = _list_drive_folder(drive_id)
            if not entries:
                return {
                    'ok': False,
                    'error': (
                        'No files found in that Drive folder. Share it as '
                        '"Anyone with the link can view", and name files like 1200000001035-1.jpg.'
                    ),
                }
            image_entries = [
                row for row in entries
                if str(row.get('mimeType') or '').startswith('image/')
                or os.path.splitext(str(row.get('name') or ''))[1].lower() in _ALLOWED_IMAGE_EXT
            ]
            total = min(len(image_entries), _DRIVE_MAX_FILES)
            for index, row in enumerate(image_entries[:_DRIVE_MAX_FILES], start=1):
                name = str(row.get('name') or f'drive-{index}.jpg')
                _emit_import_progress(
                    progress_cb,
                    phase='importing',
                    total=total,
                    processed=index - 1,
                    updated=0,
                    failed=0,
                    current=name,
                    done=False,
                )
                try:
                    data, ext = _download_drive_file(str(row.get('id') or ''), name)
                    if not os.path.splitext(name)[1]:
                        name = f'{name}{ext}'
                    uploads.append((name, data))
                except ValueError as exc:
                    continue
        else:
            data, ext = _download_drive_file(drive_id, 'drive-image')
            label = fallback_barcode or (str(int(only_item_code)) if only_item_code else 'drive-image')
            uploads.append((f'{label}{ext}', data))
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'error': f'Could not read Google Drive: {exc}'}

    if not uploads:
        return {'ok': False, 'error': 'No images could be downloaded from that Drive link.'}

    return import_product_images_from_folder_uploads(
        uploads,
        default_location_code=default_location_code,
        replace_existing=replace_existing,
        only_item_code=only_item_code,
        fallback_barcode=fallback_barcode,
        progress_cb=progress_cb,
    )


def import_product_images_from_barcode_zip_path(
    zip_path: str,
    *,
    default_location_code: Optional[int] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Import barcode-folder images from a ZIP on disk, one product at a time."""
    ensure_itemmaster_image_path_column()
    default_loc = int(default_location_code or resolve_location_code())
    if not zip_path or not os.path.isfile(zip_path):
        return {'ok': False, 'error': 'Choose a ZIP of barcode folders.'}
    try:
        zip_size = os.path.getsize(zip_path)
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}
    if zip_size > _MAX_ZIP_BYTES:
        return {'ok': False, 'error': f'Images ZIP too large (max {_MAX_ZIP_LABEL}).'}
    if zip_size <= 0:
        return {'ok': False, 'error': 'Choose a ZIP of barcode folders.'}

    try:
        with zipfile.ZipFile(zip_path) as archive:
            grouped = _zip_folder_member_names(archive)
            texts = _zip_folder_copy_texts(archive)
            folder_keys = list(dict.fromkeys(list(grouped.keys()) + list(texts.keys())))
            if not folder_keys:
                return {
                    'ok': False,
                    'error': (
                        'No barcode folders found in the ZIP. Put each product in its own folder '
                        'named with the barcode, for example 1200000001035/1.jpg. '
                        'Optional: description.txt, description_ar.txt, and specifications.txt in the same folder.'
                    ),
                }
            updated = 0
            failed = 0
            kept = 0
            gallery_total = 0
            copy_total = 0
            errors: List[str] = []
            total_folders = len(folder_keys)
            _emit_import_progress(
                progress_cb,
                phase='importing',
                total=total_folders,
                processed=0,
                updated=0,
                failed=0,
                current='',
                done=False,
            )
            for barcode in folder_keys:
                names = grouped.get(barcode) or []
                _emit_import_progress(
                    progress_cb,
                    phase='importing',
                    total=total_folders,
                    processed=updated + failed,
                    updated=updated,
                    failed=failed,
                    current=barcode,
                    done=False,
                )
                files: List[Tuple[bytes, str]] = []
                if names:
                    files, read_err = _read_zip_member_images(archive, names)
                    if read_err:
                        failed += 1
                        errors.append(f'Folder {barcode}: {read_err}')
                        continue
                desc, specs, desc_ar = _folder_copy_parts(texts, barcode)
                if not files and not desc and not specs and not desc_ar:
                    failed += 1
                    errors.append(f'Folder {barcode}: No images in folder.')
                    continue
                one = _import_barcode_folder_images(
                    {barcode: files},
                    default_loc,
                    texts=texts,
                    replace_existing=replace_existing,
                )
                updated += int(one.get('updated') or 0)
                failed += int(one.get('failed') or 0)
                kept += int(one.get('kept') or 0)
                gallery_total += int(one.get('gallery_total') or 0)
                copy_total += int(one.get('copy_total') or 0)
                errors.extend(one.get('errors') or [])
            processed = updated + failed
            ok = updated > 0 and failed == 0
            partial = updated > 0 and failed > 0
            summary = f'Processed {processed} folder(s): {updated} product(s) updated'
            if kept:
                summary += f', {kept} existing image(s) kept'
            if gallery_total:
                summary += f', {gallery_total} extra gallery photo(s)'
            if copy_total:
                summary += f', {copy_total} description/specification update(s)'
            if failed:
                summary += f', {failed} failed'
            result = {
                'ok': ok or partial,
                'partial': partial,
                'processed': processed,
                'updated': updated,
                'failed': failed,
                'kept': kept,
                'errors': errors[:100],
                'error_count': len(errors),
                'gallery_total': gallery_total,
                'copy_total': copy_total,
                'message': summary,
                'location_code': default_loc,
            }
            _emit_import_progress(
                progress_cb,
                phase='done',
                total=total_folders,
                processed=processed,
                updated=updated,
                failed=failed,
                current='',
                done=True,
                message=summary,
                ok=result['ok'],
            )
            return result
    except zipfile.BadZipFile:
        return {'ok': False, 'error': 'Images ZIP is not a valid zip file.'}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


def import_product_images_from_barcode_zip(
    zip_raw: bytes,
    *,
    default_location_code: Optional[int] = None,
    zip_path: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Import images from a ZIP of barcode folders: first photo is main, the rest are gallery."""
    if zip_path:
        return import_product_images_from_barcode_zip_path(
            zip_path,
            default_location_code=default_location_code,
            progress_cb=progress_cb,
            replace_existing=replace_existing,
        )
    if not zip_raw:
        return {'ok': False, 'error': 'Choose a ZIP of barcode folders.'}
    if len(zip_raw) > _MAX_ZIP_BYTES:
        return {'ok': False, 'error': f'Images ZIP too large (max {_MAX_ZIP_LABEL}).'}
    fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='mh-img-')
    os.close(fd)
    try:
        with open(tmp_path, 'wb') as out:
            out.write(zip_raw)
        return import_product_images_from_barcode_zip_path(
            tmp_path,
            default_location_code=default_location_code,
            progress_cb=progress_cb,
            replace_existing=replace_existing,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


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
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Import ITEMMASTER images from Excel rows (+ optional ZIP of local files)."""
    ensure_itemmaster_image_path_column()
    default_loc = int(default_location_code or resolve_location_code())

    if not excel_raw:
        return {'ok': False, 'error': 'Choose an Excel file (.xlsx).'}
    if len(excel_raw) > _MAX_EXCEL_BYTES:
        return {'ok': False, 'error': 'Excel file too large (max 50 MB).'}
    if zip_raw and len(zip_raw) > _MAX_ZIP_BYTES:
        return {'ok': False, 'error': f'Images ZIP too large (max {_MAX_ZIP_LABEL}).'}

    rows, embedded_images, parse_err = _parse_xlsx_first_sheet(excel_raw, _MAX_ROWS)
    if parse_err:
        return {'ok': False, 'error': parse_err}
    if not rows:
        return {'ok': False, 'error': 'No data rows found in the Excel file.'}

    zip_index, zip_err = _index_zip_images(zip_raw or b'')
    if zip_err:
        return {'ok': False, 'error': zip_err}
    zip_folders, _folder_err = _index_zip_barcode_folders(zip_raw or b'') if zip_raw else ({}, None)

    updated = 0
    failed = 0
    kept = 0
    errors: List[str] = []

    for excel_row, row in rows:
        item_code_raw = _row_field(row, 'ItemCode', 'ITEMCODE', 'Code')
        barcode_raw = _row_field(row, 'Barcode', 'MANUFACTURERID', 'ManufacturerId')
        loc_raw = _row_field(row, 'LocationCode', 'LOCATIONCODE')
        image_url = _row_field(row, 'ImageURL', 'ImageUrl', 'URL')
        image_file = _row_field(row, 'ImageFileName', 'ImageFile', 'Filename', 'FileName')
        description = _row_field(row, 'Description', 'DESCRIPTION', 'Details')
        description_ar = _row_field(
            row,
            'DescriptionArabic',
            'DescriptionAr',
            'ArabicDescription',
            'DESCRIPTION_AR',
            'Description_AR',
        )
        specifications = _row_field(
            row,
            'Specifications',
            'Specification',
            'SPECS',
            'Features',
            'KeyFeatures',
        )
        page_url = _row_field(
            row,
            'ProductPageURL',
            'PageURL',
            'ImportURL',
            'ProductURL',
        )
        folder_name = _row_field(
            row,
            'FolderName',
            'ImageFolder',
            'Folder',
            'ImageFolderName',
        )
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

        folder_files = _lookup_zip_folder_files(
            zip_folders,
            folder_name,
            barcode_raw,
            item_code_raw,
        )
        if (
            not embedded
            and not image_url
            and not image_file
            and not folder_files
            and not description
            and not description_ar
            and not specifications
            and not page_url
        ):
            failed += 1
            errors.append(
                f'Row {excel_row}: add an image folder, image file, Description, DescriptionArabic, Specifications, or ProductPageURL.'
            )
            continue

        try:
            if page_url and (not description or not specifications):
                try:
                    from addons.ecommerce.services import product_page_import as page_import_svc

                    extracted = page_import_svc.extract_product_page(page_url)
                    description = description or str(extracted.get('description') or '').strip()
                    specifications = specifications or str(extracted.get('specifications') or '').strip()
                    if not image_url and not embedded and not image_file and not folder_files:
                        page_images = list(extracted.get('image_urls') or [])
                        if page_images:
                            image_url = str(page_images[0] or '').strip()
                except Exception as exc:
                    errors.append(f'Row {excel_row}: could not read product page ({exc}).')

            if folder_files and not embedded and not image_file:
                existing = _item_existing_image_path(item_code, loc)
                skip_images = bool(existing) and not replace_existing
                if skip_images:
                    kept += 1
                else:
                    ok, err, _gallery = _save_item_images_from_files(
                        item_code,
                        loc,
                        folder_files,
                        replace_existing=replace_existing,
                    )
                    if not ok:
                        failed += 1
                        errors.append(f'Row {excel_row}: {err}')
                        continue
                if description or description_ar or specifications:
                    _d_ok, _s_ok, copy_err = _apply_imported_product_text(
                        item_code,
                        location_code=loc,
                        description=description,
                        specifications=specifications,
                        description_ar=description_ar,
                    )
                    if copy_err:
                        errors.append(f'Row {excel_row}: {copy_err}')
                updated += 1
                continue
            item = get_item_by_code(int(item_code), int(loc)) or {}
            existing = str(item.get('image_path') or item.get('IMAGE_PATH') or '').strip()
            skip_images = bool(existing) and not replace_existing
            rel_path = ''
            has_image_source = bool(embedded or image_file or image_url)
            if has_image_source and skip_images:
                kept += 1
            elif embedded:
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

            if rel_path:
                ok, db_err = set_item_image_path(item_code, loc, rel_path)
                if not ok:
                    failed += 1
                    errors.append(f'Row {excel_row}: {db_err or "Could not save image path."}')
                    continue
                _replace_existing_item_images(
                    int(item_code),
                    int(loc),
                    keep_rel_path=rel_path,
                    previous_path=existing,
                )
            if description or description_ar or specifications:
                _d_ok, _s_ok, copy_err = _apply_imported_product_text(
                    item_code,
                    location_code=loc,
                    description=description,
                    specifications=specifications,
                    description_ar=description_ar,
                )
                if copy_err:
                    errors.append(f'Row {excel_row}: {copy_err}')
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
    if kept:
        summary += f', {kept} existing image(s) kept'
    if failed:
        summary += f', {failed} failed'
    return {
        'ok': ok or partial,
        'partial': partial,
        'processed': processed,
        'updated': updated,
        'failed': failed,
        'kept': kept,
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


# Oracle treats '' as NULL, so TRIM(col) <> '' never matches. Use LENGTH(TRIM(...)).
_HAS_IMAGE_SQL = 'im.IMAGE_PATH IS NOT NULL AND LENGTH(TRIM(im.IMAGE_PATH)) > 0'
_MISSING_IMAGE_SQL = (
    'im.IMAGE_PATH IS NULL OR LENGTH(TRIM(im.IMAGE_PATH)) = 0 '
    'OR LENGTH(TRIM(im.IMAGE_PATH)) IS NULL'
)
_HAS_IMAGE_UPDATE_SQL = 'IMAGE_PATH IS NOT NULL AND LENGTH(TRIM(IMAGE_PATH)) > 0'


def count_items_missing_images(location_code: Optional[int] = None) -> int:
    """How many SKUs at this location have no Item Master image."""
    ensure_itemmaster_image_path_column()
    loc = int(location_code or resolve_location_code())
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS pending_count
        FROM ITEMMASTER im
        WHERE im.LOCATIONCODE = :loc
          AND ({_MISSING_IMAGE_SQL})
        """,
        {'loc': loc},
    )
    if not rows:
        return 0
    try:
        return int(rows[0].get('pending_count') or 0)
    except (TypeError, ValueError):
        return 0


def count_items_with_images(location_code: Optional[int] = None) -> int:
    """How many SKUs at this location have an Item Master image."""
    ensure_itemmaster_image_path_column()
    loc = int(location_code or resolve_location_code())
    rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS image_count
        FROM ITEMMASTER im
        WHERE im.LOCATIONCODE = :loc
          AND {_HAS_IMAGE_SQL}
        """,
        {'loc': loc},
    )
    if not rows:
        return 0
    try:
        return int(rows[0].get('image_count') or 0)
    except (TypeError, ValueError):
        return 0


def count_product_gallery_images() -> int:
    """Active extra product gallery images in MH_MEDIA."""
    try:
        from addons.ecommerce import media_db

        if not media_db.media_table_ready():
            return 0
        rows = _safe_rows(
            """
            SELECT COUNT(*) AS cnt
            FROM MH_MEDIA
            WHERE IS_ACTIVE = 1
              AND PLACEMENT IN ('product', 'product_detail')
            """,
            {},
        )
        if not rows:
            return 0
        return int(rows[0].get('cnt') or 0)
    except Exception:  # noqa: BLE001
        return 0


def _delete_local_image(rel_path: str) -> bool:
    rel = str(rel_path or '').strip().lstrip('/')
    if not rel or rel.startswith(('http://', 'https://', 'data:')):
        return False
    if rel.startswith('static/'):
        rel = rel[7:]
    full = os.path.join(_itemmaster_static_root(), 'static', rel.replace('/', os.sep))
    try:
        if os.path.isfile(full):
            os.remove(full)
            return True
    except OSError:
        return False
    return False


def _delete_location_item_image_files(location_code: int) -> int:
    """Delete leftover Item Master image files saved for this location."""
    target_dir = os.path.join(_itemmaster_static_root(), 'static', 'uploads', 'itemmaster')
    prefix = f'item_{int(location_code)}_'
    deleted = 0
    if not os.path.isdir(target_dir):
        return 0
    try:
        names = os.listdir(target_dir)
    except OSError:
        return 0
    for name in names:
        if not name.startswith(prefix):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _ALLOWED_IMAGE_EXT:
            continue
        full = os.path.join(target_dir, name)
        try:
            if os.path.isfile(full):
                os.remove(full)
                deleted += 1
        except OSError:
            continue
    return deleted


def remove_all_product_images(
    location_code: Optional[int] = None,
    *,
    remove_gallery: bool = False,
) -> Dict[str, Any]:
    """Clear ITEMMASTER.IMAGE_PATH for every SKU at this location."""
    ensure_itemmaster_image_path_column()
    loc = int(location_code or resolve_location_code())
    paths = _safe_rows(
        f"""
        SELECT im.IMAGE_PATH AS image_path
        FROM ITEMMASTER im
        WHERE im.LOCATIONCODE = :loc
          AND {_HAS_IMAGE_SQL}
        """,
        {'loc': loc},
    )
    image_paths = [
        str(row.get('image_path') or row.get('IMAGE_PATH') or '').strip()
        for row in (paths or [])
    ]
    image_paths = [path for path in image_paths if path]
    cleared = 0
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE ITEMMASTER
                    SET IMAGE_PATH = NULL
                    WHERE LOCATIONCODE = :loc
                      AND {_HAS_IMAGE_UPDATE_SQL}
                    """,
                    {'loc': loc},
                )
                cleared = int(cur.rowcount or 0)
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return {
            'ok': False,
            'cleared': 0,
            'files_deleted': 0,
            'gallery_removed': 0,
            'error': str(exc),
            'message': 'Could not remove product images.',
        }

    if cleared <= 0:
        cleared = len(image_paths)

    files_deleted = 0
    seen: set[str] = set()
    for path in image_paths:
        if path in seen:
            continue
        seen.add(path)
        if _delete_local_image(path):
            files_deleted += 1
    files_deleted += _delete_location_item_image_files(loc)

    gallery_removed = 0
    if remove_gallery:
        try:
            from addons.ecommerce import media_db

            if media_db.media_table_ready():
                with _get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE MH_MEDIA
                            SET IS_ACTIVE = 0, MODIFIED_AT = SYSTIMESTAMP
                            WHERE IS_ACTIVE = 1
                              AND PLACEMENT IN ('product', 'product_detail')
                            """
                        )
                        gallery_removed = int(cur.rowcount or 0)
                    conn.commit()
        except Exception as exc:  # noqa: BLE001
            return {
                'ok': True,
                'cleared': cleared,
                'files_deleted': files_deleted,
                'gallery_removed': 0,
                'partial': True,
                'error': str(exc),
                'message': (
                    f'Removed {cleared} main product image'
                    f'{"" if cleared == 1 else "s"}, but gallery images could not be cleared.'
                ),
            }

    if cleared <= 0 and gallery_removed <= 0:
        return {
            'ok': True,
            'cleared': 0,
            'files_deleted': 0,
            'gallery_removed': 0,
            'message': 'No product images to remove.',
        }

    parts = [f'Removed {cleared} main product image{"" if cleared == 1 else "s"}']
    if gallery_removed:
        parts.append(
            f'cleared {gallery_removed} extra gallery image{"" if gallery_removed == 1 else "s"}'
        )
    return {
        'ok': True,
        'cleared': cleared,
        'files_deleted': files_deleted,
        'gallery_removed': gallery_removed,
        'message': f'{parts[0]}.' if len(parts) == 1 else f'{parts[0]} and {parts[1]}.',
    }


def _list_items_missing_images(location_code: int, *, limit: int = 25) -> List[Dict[str, Any]]:
    ensure_itemmaster_image_path_column()
    lim = max(1, min(int(limit or 25), 100))
    rows = _safe_rows(
        f"""
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
          AND ({_MISSING_IMAGE_SQL})
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
    try:
        return url_for('static', filename=raw)
    except Exception:
        return f'/static/{raw.lstrip("/")}'


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
    pending_remaining = count_items_missing_images(loc)
    summary = f'Checked {processed} product(s): {updated} image(s) fetched'
    if skipped:
        summary += f', {skipped} not found on web'
    if failed:
        summary += f', {failed} failed'
    summary += f'. {pending_remaining} SKU(s) still pending image.'
    return {
        'ok': ok or partial,
        'partial': partial,
        'processed': processed,
        'updated': updated,
        'skipped': skipped,
        'failed': failed,
        'pending_remaining': pending_remaining,
        'errors': errors[:100],
        'error_count': len(errors),
        'message': summary,
        'location_code': loc,
    }
