"""Storefront media admin services."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from addons.ecommerce import media_db

_ADDON_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = _ADDON_ROOT / 'uploads' / 'media'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v'}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024

MIME_TO_EXT = {
    'video/mp4': '.mp4',
    'video/webm': '.webm',
    'video/quicktime': '.mov',
    'video/x-m4v': '.m4v',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/avif': '.avif',
    'image/gif': '.gif',
    'image/svg+xml': '.svg',
}

PLACEMENT_LABELS = {
    'storefront_logo': 'Storefront logo',
    'hero_bg': 'Hero background',
    'hero': 'Hero slides',
    'promo': 'Promo tiles',
    'showcase_banner': 'Showcase banners',
    'category': 'Category images',
    'explore_category': 'Explore category tiles',
    'brand': 'Brand logos',
    'age_group': 'Age group images',
    'product': 'Product gallery images',
    'product_detail': 'Product specifications (internal)',
}


def _empty_form() -> Dict[str, Any]:
    return {
        'media_id': '',
        'placement': 'hero',
        'ref_key': '',
        'title': '',
        'subtitle': '',
        'title_ar': '',
        'subtitle_ar': '',
        'image_url': '',
        'link_url': '',
        'alt_text': '',
        'sort_order': 0,
        'is_active': True,
        'meta_json': '{}',
    }


def media_to_form(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'media_id': row.get('media_id') or '',
        'placement': row.get('placement') or 'hero',
        'ref_key': row.get('ref_key') or '',
        'title': row.get('title') or '',
        'subtitle': row.get('subtitle') or '',
        'title_ar': row.get('title_ar') or '',
        'subtitle_ar': row.get('subtitle_ar') or '',
        'image_url': row.get('image_url') or '',
        'link_url': row.get('link_url') or '',
        'alt_text': row.get('alt_text') or '',
        'sort_order': row.get('sort_order') or 0,
        'is_active': row.get('is_active', True),
        'meta_json': json.dumps(row.get('meta') or {}, indent=2),
    }


def uploads_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def normalize_image_url(image_url: str) -> str:
    value = (image_url or '').strip()
    if not value:
        return value
    if '/ecommerce/media/files/' in value:
        filename = value.split('/ecommerce/media/files/')[-1]
        return f'/media/files/{filename}'
    if value.startswith('/media/files/'):
        return value
    return value


def preview_filename(image_url: str | None) -> Optional[str]:
    if not image_url:
        return None
    value = str(image_url).strip()
    if '/media/files/' in value:
        return value.split('/media/files/')[-1].lstrip('/')
    if value.startswith('/ecommerce/media/files/'):
        return value.split('/ecommerce/media/files/')[-1].lstrip('/')
    if not value.startswith('/') and not value.lower().startswith(('http://', 'https://', 'data:')):
        return value.lstrip('/')
    return None


def is_video_url(url: str | None) -> bool:
    value = (url or '').strip().lower().split('?', 1)[0]
    return any(value.endswith(ext) for ext in VIDEO_EXTENSIONS)


def _upload_mimetype(file_storage) -> str:
    for attr in ('content_type', 'mimetype'):
        value = getattr(file_storage, attr, None)
        if value:
            return str(value).split(';', 1)[0].strip().lower()
    return ''


def _resolve_upload_extension(filename: str, mimetype: str) -> str:
    ext = Path(filename or '').suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return ext
    return MIME_TO_EXT.get(mimetype, ext)


def media_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {'.mp4', '.m4v'}:
        return 'video/mp4'
    if ext == '.webm':
        return 'video/webm'
    if ext == '.mov':
        return 'video/quicktime'
    if ext == '.svg':
        return 'image/svg+xml'
    if ext == '.webp':
        return 'image/webp'
    if ext == '.avif':
        return 'image/avif'
    if ext in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if ext == '.png':
        return 'image/png'
    if ext == '.gif':
        return 'image/gif'
    return 'application/octet-stream'


def save_upload(file_storage) -> Tuple[bool, str, Optional[str]]:
    if not file_storage or not getattr(file_storage, 'filename', None):
        return False, 'No file uploaded', None
    content = file_storage.read()
    original = file_storage.filename or 'upload.jpg'
    mimetype = _upload_mimetype(file_storage)
    ext = _resolve_upload_extension(original, mimetype)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return False, f'Unsupported file type: {ext or mimetype or "unknown"}. Allowed: {allowed}', None
    max_bytes = MAX_VIDEO_UPLOAD_BYTES if ext in VIDEO_EXTENSIONS else MAX_IMAGE_UPLOAD_BYTES
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        return False, f'File exceeds {limit_mb} MB upload limit', None
    if ext in VIDEO_EXTENSIONS and len(content) < 1024:
        return False, 'Video file is too small or corrupt — please re-upload the clip', None
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', Path(original).stem)[:40]
    filename = f'{uuid.uuid4().hex[:12]}-{safe_name}{ext}'
    target = uploads_dir() / filename
    target.write_bytes(content)
    return True, 'File uploaded', f'/media/files/{filename}'


def save_bytes(content: bytes, ext: str, *, stem: str = 'web-fetch') -> Tuple[bool, str, Optional[str]]:
    """Save downloaded image bytes into uploads/media."""
    normalized_ext = ext.lower() if str(ext).startswith('.') else f'.{str(ext).lower()}'
    if normalized_ext not in IMAGE_EXTENSIONS:
        normalized_ext = '.jpg'
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        return False, 'Downloaded image exceeds 5 MB upload limit.', None
    if len(content) < 256:
        return False, 'Downloaded file is too small to be a valid image.', None
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', (stem or 'web-fetch'))[:40]
    filename = f'{uuid.uuid4().hex[:12]}-{safe_name}{normalized_ext}'
    target = uploads_dir() / filename
    target.write_bytes(content)
    return True, 'Image saved', f'/media/files/{filename}'


def save_bytes(content: bytes, ext: str, *, stem: str = 'web-fetch') -> Tuple[bool, str, Optional[str]]:
    """Save downloaded image bytes into uploads/media."""
    normalized_ext = ext.lower() if str(ext).startswith('.') else f'.{str(ext).lower()}'
    if normalized_ext not in IMAGE_EXTENSIONS:
        normalized_ext = '.jpg'
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        return False, 'Downloaded image exceeds 5 MB upload limit.', None
    if len(content) < 256:
        return False, 'Downloaded file is too small to be a valid image.', None
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', (stem or 'web-fetch'))[:40]
    filename = f'{uuid.uuid4().hex[:12]}-{safe_name}{normalized_ext}'
    target = uploads_dir() / filename
    target.write_bytes(content)
    return True, 'Image saved', f'/media/files/{filename}'


def _product_images_svc():
    try:
        from addons.ecommerce.services import product_images as product_images_svc
    except ImportError as exc:  # pragma: no cover
        raise ValueError(f'Web fetch unavailable: {exc}') from exc
    if not getattr(product_images_svc, 'requests', None):
        raise ValueError('Web fetch requires the requests library (pip install requests).')
    return product_images_svc


def _build_web_search_query(
    title: str,
    *,
    subtitle: str = '',
    ref_key: str = '',
    placement: str = '',
) -> Tuple[str, str]:
    query_parts = [str(title or '').strip()]
    if str(subtitle or '').strip():
        query_parts.append(str(subtitle).strip())
    if str(ref_key or '').strip():
        query_parts.append(str(ref_key).strip())
    if str(placement or '').strip() and str(placement).strip() not in query_parts:
        query_parts.append(str(placement).replace('_', ' ').strip())

    query = ' '.join(part for part in query_parts if part).strip()
    if len(query) < 2:
        raise ValueError('Enter a title to search for an image.')
    return query, f'{query} photo'


def search_images_from_web_by_title(
    title: str,
    *,
    subtitle: str = '',
    ref_key: str = '',
    placement: str = '',
    limit: int = 12,
) -> Dict[str, Any]:
    """Return multiple web image URLs for the user to choose from."""
    try:
        product_images_svc = _product_images_svc()
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}

    try:
        query, search_query = _build_web_search_query(
            title,
            subtitle=subtitle,
            ref_key=ref_key,
            placement=placement,
        )
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}

    urls = product_images_svc._search_bing_image_urls(search_query, limit=max(4, min(int(limit or 12), 20)))
    if not urls:
        return {'ok': False, 'error': f'No images found for “{query}”.', 'query': search_query}

    return {
        'ok': True,
        'message': f'Found {len(urls)} image options.',
        'query': search_query,
        'candidates': [{'url': url} for url in urls],
    }


def download_image_from_web_url(source_url: str, *, stem: str = 'web-fetch') -> Dict[str, Any]:
    """Download one chosen web image into uploads/media."""
    try:
        product_images_svc = _product_images_svc()
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}

    url = str(source_url or '').strip()
    if not url.lower().startswith(('http://', 'https://')):
        return {'ok': False, 'error': 'Invalid image URL.'}

    try:
        data, ext = product_images_svc._download_image(url)
        if ext in VIDEO_EXTENSIONS:
            return {'ok': False, 'error': 'Selected file is a video, not an image.'}
        ok, message, image_url = save_bytes(data, ext, stem=stem[:40] or 'web-fetch')
        if not ok or not image_url:
            return {'ok': False, 'error': message or 'Could not save image.'}
        return {
            'ok': True,
            'message': 'Image saved to your media library.',
            'image_url': image_url,
            'source_url': url,
        }
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)}


def fetch_image_from_web_by_title(
    title: str,
    *,
    subtitle: str = '',
    ref_key: str = '',
    placement: str = '',
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Download a chosen web image, or fall back to the first search result."""
    if source_url:
        try:
            query, _ = _build_web_search_query(
                title,
                subtitle=subtitle,
                ref_key=ref_key,
                placement=placement,
            )
        except ValueError:
            query = 'web-fetch'
        return download_image_from_web_url(source_url, stem=query[:40])

    search = search_images_from_web_by_title(
        title,
        subtitle=subtitle,
        ref_key=ref_key,
        placement=placement,
        limit=8,
    )
    if not search.get('ok'):
        return search

    last_error = 'Could not download any image candidate.'
    try:
        query, _ = _build_web_search_query(
            title,
            subtitle=subtitle,
            ref_key=ref_key,
            placement=placement,
        )
    except ValueError as exc:
        return {'ok': False, 'error': str(exc)}

    for candidate in search.get('candidates') or []:
        url = str((candidate or {}).get('url') or '').strip()
        if not url:
            continue
        result = download_image_from_web_url(url, stem=query[:40])
        if result.get('ok'):
            result['query'] = search.get('query')
            return result
        last_error = result.get('error') or last_error

    return {'ok': False, 'error': last_error, 'query': search.get('query')}


def resolve_file_path(filename: str) -> Optional[Path]:
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return None
    path = uploads_dir() / filename
    return path if path.is_file() else None


def strip_light_logo_background(image_url: str, *, threshold: int = 238) -> str:
    """Convert logo uploads with white/light backgrounds to PNG with transparency."""
    preview = preview_filename(image_url)
    if not preview:
        return image_url
    src = uploads_dir() / preview
    if not src.is_file():
        return image_url
    ext = src.suffix.lower()
    if ext in {'.svg', '.gif'}:
        return image_url

    try:
        from PIL import Image
    except ImportError:
        return image_url

    try:
        img = Image.open(src).convert('RGBA')
        pixels = img.load()
        width, height = img.size
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = pixels[x, y]
                if alpha == 0:
                    continue
                if red >= threshold and green >= threshold and blue >= threshold:
                    pixels[x, y] = (red, green, blue, 0)
                    continue
                # Soften near-white edges for a cleaner cutout on cream backgrounds.
                avg = (red + green + blue) / 3
                if avg >= threshold - 18:
                    fade = int(max(0, min(255, (threshold - avg) * 14)))
                    pixels[x, y] = (red, green, blue, min(alpha, fade))

        out_name = f'{src.stem}-transparent.png'
        out_path = uploads_dir() / out_name
        alpha = img.split()[-1]
        bbox = alpha.getbbox()
        if bbox:
            img = img.crop(bbox)
        img.save(out_path, 'PNG', optimize=True)
        return f'/media/files/{out_name}'
    except Exception:
        return image_url


def list_media_page(*, placement: Optional[str] = None) -> Dict[str, Any]:
    rows, warning = media_db.list_media(placement=placement, active_only=False)
    logo_rows, _ = media_db.list_media(placement='storefront_logo', active_only=False)
    logo_item = logo_rows[0] if logo_rows else None
    return {
        'media_items': rows,
        'logo_item': logo_item,
        'warning': warning,
        'tables_ready': media_db.media_table_ready(),
        'placements': media_db.PLACEMENTS,
        'placement_labels': PLACEMENT_LABELS,
        'placement_filter': placement or '',
    }


def get_create_form() -> Dict[str, Any]:
    return _empty_form()


def get_edit_form(media_id: int) -> Optional[Dict[str, Any]]:
    row = media_db.get_media(media_id)
    if not row:
        return None
    return media_to_form(row)


def _form_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').lower() in ('1', 'true', 'on', 'yes')


def build_payload_from_form(
    form: Dict[str, str],
    uploaded_path: Optional[str] = None,
    poster_path: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    placement = (form.get('placement') or '').strip()
    if placement not in media_db.PLACEMENTS:
        return False, f'Invalid placement: {placement}', None

    image_url = normalize_image_url(uploaded_path or (form.get('image_url') or '').strip())
    if not image_url:
        return False, 'Media URL or uploaded file is required.', None

    meta_raw = (form.get('meta_json') or '').strip() or '{}'
    try:
        meta = json.loads(meta_raw)
        if not isinstance(meta, dict):
            return False, 'Meta JSON must be an object.', None
    except json.JSONDecodeError:
        return False, 'Meta JSON is invalid.', None

    if poster_path:
        meta['poster_url'] = normalize_image_url(poster_path)

    media_id_raw = (form.get('media_id') or '').strip()
    payload: Dict[str, Any] = {
        'placement': placement,
        'ref_key': (form.get('ref_key') or '').strip() or None,
        'title': (form.get('title') or '').strip() or None,
        'subtitle': (form.get('subtitle') or '').strip() or None,
        'title_ar': (form.get('title_ar') or '').strip() or None,
        'subtitle_ar': (form.get('subtitle_ar') or '').strip() or None,
        'image_url': image_url,
        'link_url': (form.get('link_url') or '').strip() or None,
        'alt_text': (form.get('alt_text') or '').strip() or None,
        'sort_order': int(form.get('sort_order') or 0),
        'is_active': _form_bool(form.get('is_active')),
        'meta': meta,
    }
    if media_id_raw:
        try:
            payload['media_id'] = int(media_id_raw)
        except ValueError:
            return False, 'Invalid media id.', None
    return True, '', payload


def save_media(
    form: Dict[str, str],
    file_storage=None,
    poster_storage=None,
) -> Tuple[bool, str]:
    uploaded_path = None
    if file_storage and getattr(file_storage, 'filename', None):
        ok, message, path = save_upload(file_storage)
        if not ok:
            return False, message
        uploaded_path = path

    poster_path = None
    if poster_storage and getattr(poster_storage, 'filename', None):
        ok, message, path = save_upload(poster_storage)
        if not ok:
            return False, message
        poster_path = path

    ok, message, payload = build_payload_from_form(
        form,
        uploaded_path=uploaded_path,
        poster_path=poster_path,
    )
    if not ok or not payload:
        return False, message
    success, result_message, _ = media_db.upsert_media(payload)
    return success, result_message


def deactivate_media(media_id: int) -> Tuple[bool, str]:
    return media_db.deactivate_media(media_id)


def _deactivate_other_logos(keep_media_id: Optional[int] = None) -> None:
    rows, _ = media_db.list_media(placement='storefront_logo', active_only=False)
    for row in rows:
        media_id = row.get('media_id')
        if not media_id or media_id == keep_media_id:
            continue
        if row.get('is_active'):
            media_db.deactivate_media(int(media_id))


def save_storefront_logo(
    form: Dict[str, str],
    file_storage=None,
) -> Tuple[bool, str]:
    """Save header/footer logo — always uses placement storefront_logo."""
    uploaded_path = None
    if file_storage and getattr(file_storage, 'filename', None):
        ok, message, path = save_upload(file_storage)
        if not ok:
            return False, message
        uploaded_path = path

    existing_rows, _ = media_db.list_media(placement='storefront_logo', active_only=False)
    existing = existing_rows[0] if existing_rows else None

    image_url = normalize_image_url(
        uploaded_path or (form.get('image_url') or '').strip() or (existing or {}).get('image_url') or ''
    )
    if not image_url:
        return False, 'Upload a logo image (PNG, SVG, JPG, or WebP).'

    image_url = strip_light_logo_background(image_url)

    media_id_raw = (form.get('media_id') or '').strip()
    media_id: Optional[int] = None
    if media_id_raw:
        try:
            media_id = int(media_id_raw)
        except ValueError:
            return False, 'Invalid media id.'
    elif existing:
        media_id = int(existing['media_id'])

    payload: Dict[str, Any] = {
        'placement': 'storefront_logo',
        'ref_key': 'header',
        'title': (form.get('title') or '').strip() or 'MamaHub logo',
        'subtitle': None,
        'image_url': image_url,
        'link_url': None,
        'alt_text': (form.get('alt_text') or '').strip() or 'MamaHub',
        'sort_order': 0,
        'is_active': True,
        'meta': {},
    }
    if media_id:
        payload['media_id'] = media_id

    success, result_message, saved = media_db.upsert_media(payload)
    if success and saved:
        _deactivate_other_logos(saved.get('media_id'))
    return success, result_message
