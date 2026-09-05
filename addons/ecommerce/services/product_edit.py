"""Inline product edits for ecommerce Products page (ITEMMASTER)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from nexa_http import current_app, url_for

from addons.ecommerce.services.common import resolve_location_code
from addons.ecommerce.services import media as media_svc
from addons.ecommerce.services import product_images as product_images_svc
from addons.ecommerce.services import product_web_meta as web_meta_svc
from db import (
    _detect_column,
    _detect_table,
    _fetch_rows,
    _get_connection,
    _get_table_columns,
    ensure_itemmaster_image_path_column,
    set_item_image_path,
)
from addons.ecommerce import media_db

_ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def product_image_public_url(image_path: Optional[str]) -> Optional[str]:
    """Build a browser URL for ITEMMASTER.IMAGE_PATH."""
    raw = str(image_path or '').strip()
    if not raw:
        return None
    if raw.startswith(('http://', 'https://', 'data:')):
        return raw
    if raw.startswith('/api/'):
        return raw
    if raw.startswith('/'):
        return raw
    return url_for('static', filename=raw)


def update_product_row(
    *,
    item_code: int,
    location_code: Optional[int] = None,
    item_name: Optional[str] = None,
    description: Optional[str] = None,
    specifications: Optional[str] = None,
    description_ar: Optional[str] = None,
    specifications_ar: Optional[str] = None,
    retail_price: Optional[str] = None,
    offer_price: Optional[str] = None,
    image_upload: Any = None,
    remove_image: bool = False,
    gallery_uploads: Optional[List[Any]] = None,
    remove_gallery_ids: Optional[List[Any]] = None,
) -> Tuple[bool, str]:
    """Update name, description, retail price, and optional image for one product."""
    loc = int(location_code or resolve_location_code())
    ic = int(item_code)
    if ic <= 0:
        return (False, 'Invalid item code.')

    ensure_itemmaster_image_path_column()
    im = _detect_table(['ITEMMASTER', 'itemmaster', 'ITEM_MASTER'])
    if not im:
        return (False, 'ITEMMASTER not found.')
    cols = {c.upper() for c in _get_table_columns(im) or []}
    code_col = _detect_column(im, ['ITEMCODE', 'ITEM_CODE', 'itemcode'])
    loc_col = _detect_column(im, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
    if not code_col:
        return (False, 'Invalid item table.')

    set_parts: list[str] = []
    params: Dict[str, Any] = {'ic': ic, 'loc': loc}

    name_val = str(item_name or '').strip()
    if not name_val:
        return (False, 'Item name is required.')
    if 'ITEMNAME' in cols:
        set_parts.append('ITEMNAME = :item_name')
        params['item_name'] = name_val[:200]

    if description is not None and 'DESCRIPTION' in cols:
        set_parts.append('DESCRIPTION = :description')
        params['description'] = str(description or '').strip()[:500]

    if retail_price is not None and 'RETAILPRICE' in cols:
        try:
            price = float(str(retail_price).strip() or '0')
        except (TypeError, ValueError):
            return (False, 'Retail price must be a number.')
        if price < 0:
            return (False, 'Retail price cannot be negative.')
        set_parts.append('RETAILPRICE = :retail_price')
        params['retail_price'] = price

    offer_saved: Optional[float] = None
    if offer_price is not None and 'WHOLESALEPRICE' in cols:
        try:
            offer = float(str(offer_price).strip() or '0')
        except (TypeError, ValueError):
            return (False, 'Offer price must be a number.')
        if offer < 0:
            return (False, 'Offer price cannot be negative.')
        set_parts.append('WHOLESALEPRICE = :offer_price')
        params['offer_price'] = offer
        offer_saved = offer
    elif offer_price is not None and 'WHOLESALEPRICE' not in cols:
        return (False, 'Offer price cannot be saved — WHOLESALEPRICE column is missing on ITEMMASTER.')

    gallery_files = [
        upload
        for upload in (gallery_uploads or [])
        if upload and str(getattr(upload, 'filename', '') or '').strip()
    ]
    gallery_remove_ids = [
        raw_id for raw_id in (remove_gallery_ids or []) if str(raw_id or '').strip()
    ]

    if not set_parts and specifications is None and description_ar is None and specifications_ar is None and not remove_image and not gallery_files and not gallery_remove_ids and not (
        image_upload and str(getattr(image_upload, 'filename', '') or '').strip()
    ):
        return (False, 'Nothing to save.')

    try:
        conn_ctx = _get_connection()
        with conn_ctx as conn:
            with conn.cursor() as cur:
                if set_parts:
                    where = [f'{code_col} = :ic']
                    if loc_col:
                        where.append(f'{loc_col} = :loc')
                    sql = f"UPDATE {im} SET {', '.join(set_parts)} WHERE {' AND '.join(where)}"
                    cur.execute(sql, params)
                    if cur.rowcount == 0:
                        conn.rollback()
                        return (False, 'Item not found for this location.')

            conn.commit()
    except Exception as exc:  # noqa: BLE001
        return (False, str(exc))

    existing_path = ''
    if 'IMAGE_PATH' in cols:
        try:
            where = [f'{code_col} = :ic']
            p: Dict[str, Any] = {'ic': ic}
            if loc_col:
                where.append(f'{loc_col} = :loc')
                p['loc'] = loc
            _, rows = _fetch_rows(
                f"SELECT IMAGE_PATH AS image_path FROM {im} WHERE {' AND '.join(where)}",
                p,
            )
            if rows:
                existing_path = str(rows[0].get('image_path') or rows[0].get('IMAGE_PATH') or '').strip()
        except Exception:  # noqa: BLE001
            existing_path = ''

    upload_name = str(getattr(image_upload, 'filename', '') or '').strip()
    if remove_image or upload_name:
        new_path = existing_path
        if remove_image:
            new_path = ''
        elif upload_name:
            ext = os.path.splitext(upload_name)[1].lower()
            if ext not in _ALLOWED_IMAGE_EXT:
                return (False, 'Image must be PNG, JPG, JPEG, WEBP, or GIF.')
            data = image_upload.read()
            if not isinstance(data, bytes):
                data = bytes(data) if data else b''
            if not data:
                return (False, 'Image file is empty.')
            try:
                new_path = product_images_svc._save_item_image_bytes(
                    data,
                    ext,
                    location_code=loc,
                    item_code=ic,
                )
            except ValueError as exc:
                return (False, str(exc))

        ok, err = set_item_image_path(ic, loc, new_path or None)
        if not ok:
            return (False, err or 'Could not save image.')
        if (remove_image or upload_name) and existing_path and existing_path != new_path:
            _delete_static_image(existing_path)

    if specifications is not None:
        spec_ok, spec_msg = web_meta_svc.save_product_web_meta(
            ic,
            specifications=specifications,
            touch_specs=True,
            fallback_image=existing_path,
        )
        if not spec_ok:
            return (False, spec_msg)

    if description_ar is not None:
        desc_ar_ok, desc_ar_msg = web_meta_svc.save_product_web_meta(
            ic,
            description_ar=description_ar,
            touch_description_ar=True,
            fallback_image=existing_path,
        )
        if not desc_ar_ok:
            return (False, desc_ar_msg)

    if specifications_ar is not None:
        spec_ar_ok, spec_ar_msg = web_meta_svc.save_product_web_meta(
            ic,
            specifications_ar=specifications_ar,
            touch_specs_ar=True,
            fallback_image=existing_path,
        )
        if not spec_ar_ok:
            return (False, spec_ar_msg)

    if offer_price is not None:
        offer_ok, offer_msg = web_meta_svc.save_product_web_meta(
            ic,
            offer_price=offer_price,
            touch_offer=True,
            fallback_image=existing_path,
        )
        if not offer_ok:
            return (False, offer_msg)

    gallery_ok, gallery_msg = sync_product_gallery(
        ic,
        gallery_uploads=gallery_files,
        remove_media_ids=gallery_remove_ids,
    )
    if not gallery_ok:
        return (False, gallery_msg)

    message = 'Product saved.'
    if offer_saved is not None and offer_saved > 0:
        retail_for_check: Optional[float] = None
        if retail_price is not None and 'RETAILPRICE' in cols:
            try:
                retail_for_check = float(str(retail_price).strip() or '0')
            except (TypeError, ValueError):
                retail_for_check = None
        if retail_for_check is None:
            try:
                where = [f'{code_col} = :ic']
                p: Dict[str, Any] = {'ic': ic}
                if loc_col:
                    where.append(f'{loc_col} = :loc')
                    p['loc'] = loc
                _, rows = _fetch_rows(
                    f"SELECT NVL(RETAILPRICE, 0) AS retailprice FROM {im} WHERE {' AND '.join(where)}",
                    p,
                )
                if rows:
                    retail_for_check = float(rows[0].get('retailprice') or 0)
            except Exception:  # noqa: BLE001
                retail_for_check = None
        if retail_for_check is not None and offer_saved >= retail_for_check:
            message += (
                ' Offer was saved, but it must be lower than retail to show as a sale on the app.'
            )

    return (True, message)


def sync_product_gallery(
    item_code: int,
    *,
    gallery_uploads: Optional[List[Any]] = None,
    remove_media_ids: Optional[List[Any]] = None,
) -> Tuple[bool, str]:
    """Add or remove MH_MEDIA rows for product gallery images."""
    uploads = list(gallery_uploads or [])
    remove_ids = list(remove_media_ids or [])
    if not uploads and not remove_ids:
        return (True, '')

    if not media_db.media_table_ready():
        return (
            False,
            'Gallery images require the MH_MEDIA table. Run the MamaHub media schema script first.',
        )

    ic = int(item_code)
    rows, _ = media_db.list_media(placement='product', active_only=False)
    product_rows = [row for row in rows if str(row.get('ref_key') or '').strip() == str(ic)]

    for raw_id in remove_ids:
        try:
            media_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        row = next((r for r in product_rows if int(r.get('media_id') or 0) == media_id), None)
        if not row:
            continue
        ok, msg = media_db.deactivate_media(media_id)
        if not ok:
            return (False, msg or 'Could not remove gallery image.')
        product_rows = [r for r in product_rows if int(r.get('media_id') or 0) != media_id]

    if not uploads:
        return (True, '')

    sort_order = max([int(row.get('sort_order') or 0) for row in product_rows], default=0)
    for upload in uploads:
        ok, msg, path = media_svc.save_upload(upload)
        if not ok or not path:
            return (False, msg or 'Could not upload gallery image.')
        sort_order += 1
        payload = {
            'placement': 'product',
            'ref_key': str(ic),
            'title': f'Product {ic} gallery',
            'subtitle': None,
            'image_url': path,
            'link_url': None,
            'alt_text': f'Product {ic} photo',
            'sort_order': sort_order,
            'is_active': True,
            'meta': {},
        }
        ok, msg, _ = media_db.upsert_media(payload)
        if not ok:
            return (False, msg or 'Could not save gallery image.')

    return (True, '')


def _delete_static_image(rel_path: str) -> None:
    rel = str(rel_path or '').strip().lstrip('/')
    if not rel or rel.startswith(('http://', 'https://')):
        return
    if rel.startswith('static/'):
        rel = rel[7:]
    full = os.path.join(current_app.root_path, 'static', rel.replace('/', os.sep))
    try:
        if os.path.isfile(full):
            os.remove(full)
    except OSError:
        pass
