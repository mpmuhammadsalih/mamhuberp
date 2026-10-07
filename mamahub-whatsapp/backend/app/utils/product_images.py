"""Resolve ITEMMASTER image paths for CRM display and WhatsApp cards."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ITEMMASTER_DIR = Path("/var/www/mamahub/static/uploads/itemmaster")
MAMAHUB_STATIC = Path("/var/www/mamahub/static")
MEDIA_DIRS = (
    ITEMMASTER_DIR,
    Path("/var/www/mamahub/addons/ecommerce/uploads/media"),
    Path("/var/www/mamahub/static/uploads/media"),
    Path("/var/www/mamahub/static/media/files"),
)
LOGO_CANDIDATES = (
    Path("/var/www/mamahubweb/frontend/public/mamahub-logo.png"),
    Path("/var/www/mamahubweb/frontend/public/images/mamahub-logo.png"),
    Path("/var/www/mamahubweb/frontend/dist/mamahub-logo.png"),
)
_SKIP_NAMES = {"mamahub-logo.png", "product-detail-placeholder.svg"}


def image_filename(image_path: Optional[str]) -> str:
    raw = str(image_path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    name = Path(urlparse(raw).path).name
    return name if name and name not in {".", ".."} else ""


def local_product_image_by_code(itemcode: str) -> Optional[Path]:
    code = str(itemcode or "").strip()
    if not code or not ITEMMASTER_DIR.is_dir():
        return None
    matches = [path for path in ITEMMASTER_DIR.glob(f"item_*_{code}_*") if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def local_product_image(image_path: Optional[str], itemcode: Optional[str] = None) -> Optional[Path]:
    raw = str(image_path or "").strip().replace("\\", "/")
    name = image_filename(raw)
    if name.lower() in _SKIP_NAMES:
        return local_product_image_by_code(itemcode or "")
    candidates: list[Path] = []
    if name:
        candidates.append(ITEMMASTER_DIR / name)
        for folder in MEDIA_DIRS:
            candidates.append(folder / name)
    if raw and not raw.startswith(("http://", "https://", "data:")):
        rel = raw.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[7:]
        candidates.append(MAMAHUB_STATIC / rel)
        candidates.append(Path(raw))
    for path in candidates:
        try:
            if path.is_file() and path.name.lower() not in _SKIP_NAMES:
                return path
        except OSError:
            continue
    by_code = local_product_image_by_code(itemcode or "")
    if by_code:
        return by_code
    return None


def _download_image(url: str, itemcode: str) -> Optional[Path]:
    if not str(url or "").startswith("http"):
        return None
    if any(skip in url.lower() for skip in ("mamahub-logo", "placeholder")):
        return None
    try:
        import httpx

        from app.core.config import get_settings

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 MamaHubWhatsApp/1.0"},
            )
        if not response.is_success or not response.content or len(response.content) < 80:
            return None
        mime = (response.headers.get("content-type") or "").split(";")[0].lower()
        suffix = ".jpg"
        if "png" in mime or url.lower().endswith(".png"):
            suffix = ".png"
        elif "webp" in mime or url.lower().endswith(".webp"):
            suffix = ".webp"
        elif "jpeg" in mime or url.lower().endswith((".jpg", ".jpeg")):
            suffix = ".jpg"
        dest = get_settings().upload_path / f"wa-item-{itemcode}{suffix}"
        dest.write_bytes(response.content)
        return dest
    except Exception:
        logger.warning("Could not download product image for %s from %s", itemcode, url)
        return None


def stage_whatsapp_image(image_path: Optional[str], itemcode: str) -> Optional[str]:
    """Copy a real product photo into CRM uploads so WhatsApp can send it."""
    local = local_product_image(image_path, itemcode)
    if not local:
        url = str(image_path or "").strip()
        if not url.startswith("http"):
            url = public_product_image_url(image_path, "https://www.mamahub.store") or ""
        downloaded = _download_image(url, itemcode)
        if downloaded:
            return downloaded.name
        return None
    from app.core.config import get_settings

    dest = get_settings().upload_path / f"wa-item-{itemcode}{local.suffix.lower() or '.jpg'}"
    try:
        if not dest.exists() or dest.stat().st_mtime < local.stat().st_mtime:
            shutil.copy2(local, dest)
        return dest.name
    except OSError:
        return None


def public_product_image_url(image_path: Optional[str], storefront_base: str) -> Optional[str]:
    raw = str(image_path or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    name = image_filename(raw)
    if not name:
        return None
    base = (storefront_base or "https://www.mamahub.store").rstrip("/")
    return f"{base}/api/v1/products/images/{name}"


def logo_path() -> Optional[Path]:
    for path in LOGO_CANDIDATES:
        if path.is_file():
            return path
    return None
