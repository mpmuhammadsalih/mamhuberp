"""Render MamaHub storefront-style product cards for WhatsApp."""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings
from app.schemas.crm import ProductPickIn
from app.utils.product_images import local_product_image, logo_path, public_product_image_url

logger = logging.getLogger(__name__)

PINK = (255, 75, 139)
PINK_SOFT = (255, 232, 240)
PINK_CREAM = (255, 240, 246)
PINK_PILL = (255, 214, 228)
INK = (30, 41, 59)
SAGE = (100, 116, 139)
HEART = (176, 176, 184)
WHITE = (255, 255, 255)
PAGE = (255, 248, 251)
SHADOW = (255, 75, 139, 28)

CARD_W = 360
IMAGE_H = 430
DETAIL_H = 150
CARD_H = IMAGE_H + DETAIL_H
RADIUS = 28
GAP = 18
PAD = 22

_FONT_REG = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _FONT_BOLD if bold else _FONT_REG
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _title_case(value: str) -> str:
    text = " ".join((value or "").split())
    return text.title() if text else "MamaHub item"


def _money(value: float) -> str:
    currency = get_settings().company_currency or "QAR"
    return f"{currency} {float(value):.2f}"


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    img = Image.new("RGB", size, PINK_SOFT)
    pixels = img.load()
    for y in range(height):
        t = y / max(1, height - 1)
        if t < 0.55:
            u = t / 0.55
            color = (
                int(PINK_SOFT[0] + (255 - PINK_SOFT[0]) * u),
                int(PINK_SOFT[1] + (255 - PINK_SOFT[1]) * u),
                int(PINK_SOFT[2] + (255 - PINK_SOFT[2]) * u),
            )
        else:
            u = (t - 0.55) / 0.45
            color = (
                int(255 + (PINK_CREAM[0] - 255) * u),
                int(255 + (PINK_CREAM[1] - 255) * u),
                int(255 + (PINK_CREAM[2] - 255) * u),
            )
        for x in range(width):
            pixels[x, y] = color
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int = 2) -> List[str]:
    words = _title_case(text).split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            ellipsis = "…"
            while current and draw.textlength(current + ellipsis, font=font) > max_width:
                current = current[:-1]
            lines.append((current or ellipsis) + ellipsis)
            return lines[:max_lines]
    if current:
        lines.append(current)
    return lines[:max_lines]


def _draw_heart(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    s = size
    pts = [
        (cx, cy + int(s * 0.42)),
        (cx - int(s * 0.46), cy + int(s * 0.02)),
        (cx - int(s * 0.46), cy - int(s * 0.16)),
        (cx - int(s * 0.18), cy - int(s * 0.38)),
        (cx, cy - int(s * 0.16)),
        (cx + int(s * 0.18), cy - int(s * 0.38)),
        (cx + int(s * 0.46), cy - int(s * 0.16)),
        (cx + int(s * 0.46), cy + int(s * 0.02)),
    ]
    draw.line(pts + [pts[0]], fill=HEART, width=2, joint="curve")


def _open_image(source: Path | bytes) -> Optional[Image.Image]:
    try:
        if isinstance(source, Path):
            img = Image.open(source)
        else:
            img = Image.open(BytesIO(source))
        return img.convert("RGBA")
    except Exception:  # noqa: BLE001
        return None


def _fetch_bytes(url: str) -> Optional[bytes]:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.get(url)
        if response.is_success and response.content:
            return response.content
    except Exception:  # noqa: BLE001
        logger.warning("Could not fetch product image %s", url)
    return None


def _product_photo(product: ProductPickIn) -> Image.Image:
    local = local_product_image(product.image_url, product.itemcode)
    if local:
        opened = _open_image(local)
        if opened:
            return opened
    settings = get_settings()
    url = public_product_image_url(product.image_url, getattr(settings, "storefront_base_url", "") or "https://www.mamahub.store")
    if url:
        raw = _fetch_bytes(url)
        if raw:
            opened = _open_image(raw)
            if opened:
                return opened
    logo = logo_path()
    if logo:
        opened = _open_image(logo)
        if opened:
            return opened
    placeholder = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    draw = ImageDraw.Draw(placeholder)
    draw.text((40, 140), "MamaHub", font=_font(36, bold=True), fill=PINK)
    return placeholder


def _fit_contain(photo: Image.Image, box: tuple[int, int, int, int]) -> tuple[Image.Image, int, int]:
    left, top, right, bottom = box
    max_w = max(1, right - left)
    max_h = max(1, bottom - top)
    src = photo.copy()
    src.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = left + (max_w - src.width) // 2
    y = top + (max_h - src.height) // 2
    return src, x, y


def render_card(product: ProductPickIn, *, in_cart_qty: int = 0) -> Image.Image:
    card = Image.new("RGBA", (CARD_W, CARD_H), WHITE)
    image_area = _gradient((CARD_W, IMAGE_H)).convert("RGBA")
    card.paste(image_area, (0, 0))
    draw = ImageDraw.Draw(card)

    photo, px, py = _fit_contain(_product_photo(product), (28, 56, CARD_W - 28, IMAGE_H - 58))
    card.paste(photo, (px, py), photo)

    offer = float(getattr(product, "offer_price", 0) or 0)
    retail = float(product.retailprice or 0)
    on_offer = offer > 0 and retail > 0 and offer < retail
    badge_w, badge_h = 72 if on_offer else 62, 26
    draw.rounded_rectangle((16, 16, 16 + badge_w, 16 + badge_h), radius=13, fill=PINK)
    badge_font = _font(11, bold=True)
    label = "OFFER" if on_offer else "NEW"
    tw = draw.textlength(label, font=badge_font)
    draw.text((16 + (badge_w - tw) / 2, 21), label, font=badge_font, fill=WHITE)

    heart_box = (CARD_W - 50, 14, CARD_W - 14, 50)
    draw.ellipse(heart_box, fill=WHITE)
    _draw_heart(draw, CARD_W - 32, 31, 16)

    if in_cart_qty > 0:
        pill = (CARD_W - 118, IMAGE_H - 50, CARD_W - 16, IMAGE_H - 16)
        draw.rounded_rectangle(pill, radius=17, fill=PINK_PILL)
        qty_font = _font(18, bold=True)
        draw.text((CARD_W - 108, IMAGE_H - 44), "−", font=qty_font, fill=PINK)
        qty = str(int(in_cart_qty))
        qw = draw.textlength(qty, font=qty_font)
        draw.text((CARD_W - 67 - qw / 2, IMAGE_H - 44), qty, font=qty_font, fill=PINK)
        draw.text((CARD_W - 42, IMAGE_H - 44), "+", font=qty_font, fill=PINK)
    else:
        plus = (CARD_W - 52, IMAGE_H - 52, CARD_W - 16, IMAGE_H - 16)
        draw.rounded_rectangle(plus, radius=10, fill=PINK)
        plus_font = _font(24, bold=True)
        pw = draw.textlength("+", font=plus_font)
        draw.text((CARD_W - 34 - pw / 2, IMAGE_H - 50), "+", font=plus_font, fill=WHITE)

    title_font = _font(18, bold=True)
    lines = _wrap(draw, product.itemname or product.itemcode, title_font, CARD_W - 40, 2)
    y = IMAGE_H + 22
    for line in lines:
        draw.text((20, y), line, font=title_font, fill=INK)
        y += 26

    price_font = _font(22, bold=True)
    sale = offer if on_offer else retail
    draw.text((20, CARD_H - 46), _money(sale), font=price_font, fill=PINK)
    if on_offer:
        old_font = _font(13, bold=True)
        old = _money(retail)
        ox = 20 + draw.textlength(_money(sale) + "  ", font=price_font)
        draw.text((ox, CARD_H - 40), old, font=old_font, fill=SAGE)
        strike_y = CARD_H - 32
        draw.line((ox, strike_y, ox + draw.textlength(old, font=old_font), strike_y), fill=SAGE, width=2)

    mask = _rounded_mask((CARD_W, CARD_H), RADIUS)
    out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def render_catalog_image(products: Sequence[ProductPickIn]) -> Image.Image:
    pair = list(products[:2])
    cards = [render_card(item) for item in pair]
    if len(cards) == 1:
        width = CARD_W + PAD * 2
        height = CARD_H + PAD * 2
        page = Image.new("RGBA", (width, height), PAGE + (255,))
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (PAD + 4, PAD + 8, PAD + CARD_W + 4, PAD + CARD_H + 8),
            radius=RADIUS,
            fill=SHADOW,
        )
        page = Image.alpha_composite(page, shadow.filter(ImageFilter.GaussianBlur(8)))
        page.paste(cards[0], (PAD, PAD), cards[0])
        return page.convert("RGB")

    width = PAD * 2 + CARD_W * 2 + GAP
    height = CARD_H + PAD * 2
    page = Image.new("RGBA", (width, height), PAGE + (255,))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    for index in range(2):
        x = PAD + index * (CARD_W + GAP)
        sdraw.rounded_rectangle((x + 4, PAD + 8, x + CARD_W + 4, PAD + CARD_H + 8), radius=RADIUS, fill=SHADOW)
    page = Image.alpha_composite(page, shadow.filter(ImageFilter.GaussianBlur(8)))
    for index, card in enumerate(cards):
        x = PAD + index * (CARD_W + GAP)
        page.paste(card, (x, PAD), card)
    return page.convert("RGB")


def save_catalog_cards(products: Iterable[ProductPickIn], *, limit: int = 10) -> List[Tuple[Path, str]]:
    picks = [item for item in products if item.itemcode][: max(0, int(limit))]
    if not picks:
        return []
    out_dir = get_settings().upload_path
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Tuple[Path, str]] = []
    for index in range(0, len(picks), 2):
        chunk = picks[index : index + 2]
        image = render_catalog_image(chunk)
        codes = "-".join(item.itemcode for item in chunk)
        path = out_dir / f"wa-card-{codes}.jpg"
        image.save(path, "JPEG", quality=88, optimize=True)
        lines = []
        for item in chunk:
            lines.append(_title_case(item.itemname or item.itemcode))
            offer = float(getattr(item, "offer_price", 0) or 0)
            retail = float(item.retailprice or 0)
            if offer > 0 and retail > 0 and offer < retail:
                lines.append(f"{_money(offer)}  (was {_money(retail)})")
            else:
                lines.append(_money(retail))
            lines.append("")
        lines.append("Tap Choose items below to add to your list.")
        saved.append((path, "\n".join(lines).strip()))
    return saved
