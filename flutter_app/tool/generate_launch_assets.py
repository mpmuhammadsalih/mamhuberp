"""Generate Android launcher + splash assets from assets/images/nexus-erp-logo.png."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "images" / "nexus-erp-logo.png"
RES = ROOT / "android" / "app" / "src" / "main" / "res"


def _fit_contain(img: Image.Image, size: int, pad_ratio: float = 0.12) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    inner = int(size * (1 - pad_ratio * 2))
    copy = img.convert("RGBA")
    copy.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    x = (size - copy.width) // 2
    y = (size - copy.height) // 2
    canvas.paste(copy, (x, y), copy)
    return canvas


def _save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(path, format="PNG", optimize=True)


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source logo: {SRC}")

    logo = Image.open(SRC)

    mipmap_sizes = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    for folder, px in mipmap_sizes.items():
        _save_png(_fit_contain(logo, px, pad_ratio=0.08), RES / folder / "ic_launcher.png")

    fg_sizes = {
        "drawable-mdpi": 108,
        "drawable-hdpi": 162,
        "drawable-xhdpi": 216,
        "drawable-xxhdpi": 324,
        "drawable-xxxhdpi": 432,
    }
    for folder, px in fg_sizes.items():
        _save_png(_fit_contain(logo, px, pad_ratio=0.14), RES / folder / "ic_launcher_foreground.png")

    splash_sizes = {
        "drawable-mdpi": 288,
        "drawable-hdpi": 432,
        "drawable-xhdpi": 576,
        "drawable-xxhdpi": 864,
        "drawable-xxxhdpi": 1152,
    }
    for folder, px in splash_sizes.items():
        _save_png(_fit_contain(logo, px, pad_ratio=0.1), RES / folder / "splash.png")

    _save_png(_fit_contain(logo, 512, pad_ratio=0.1), RES / "drawable" / "splash.png")

    print("Generated launcher + splash PNGs under android/app/src/main/res/")


if __name__ == "__main__":
    main()
