"""Serve ITEMMASTER product images for the storefront API."""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

from nexa_http import current_app


def _itemmaster_uploads_dir() -> Path:
    return Path(current_app.root_path) / 'static' / 'uploads' / 'itemmaster'


def resolve_item_image_file(filename: str) -> Optional[Path]:
    """Resolve a safe basename under static/uploads/itemmaster."""
    safe = os.path.basename(str(filename or '').strip())
    if not safe or safe != str(filename).strip() or '..' in safe:
        return None
    path = _itemmaster_uploads_dir() / safe
    return path if path.is_file() else None


def item_image_content_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or 'application/octet-stream'


def public_item_image_url(image_path: Optional[str]) -> Optional[str]:
    """Map ITEMMASTER.IMAGE_PATH to a storefront URL under /api/v1."""
    raw = str(image_path or '').strip()
    if not raw:
        return None
    if raw.startswith(('http://', 'https://', 'data:')):
        return raw
    if raw.startswith('/api/'):
        return raw

    rel = raw.replace('\\', '/').lstrip('/')
    if rel.startswith('static/'):
        rel = rel[7:]
    marker = 'uploads/itemmaster/'
    if marker in rel:
        rel = rel.split(marker, 1)[1]
    filename = os.path.basename(rel)
    if not filename:
        return None
    return f'/api/v1/products/images/{filename}'
