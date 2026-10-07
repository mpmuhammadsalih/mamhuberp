"""Prepare MamaHub circular logo PNG with transparent outer background."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ASSETS = Path(
    r"C:\Users\admin\.cursor\projects\d-webapps-mamahub\assets"
    r"\c__Users_admin_AppData_Roaming_Cursor_User_workspaceStorage_e0baf2e299a706fbbcbae2c09aa62025_images"
    r"_ChatGPT_Image_Aug_11__2026__03_39_19_PM-d8047c4a-b575-40c1-9e20-a73a9a8e7470.png"
)
OUT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public" / "images"
OUT = OUT_DIR / "mamahub-logo.png"
SOURCE_COPY = OUT_DIR / "mamahub-logo-source.png"


def is_outer_background(r: int, g: int, b: int, a: int) -> bool:
    if a == 0:
        return True
    # Black matte outside the circular export.
    if r <= 40 and g <= 40 and b <= 40:
        return True
    # Checkerboard / white export background outside the circle.
    if r >= 235 and g >= 235 and b >= 235:
        return True
    if r >= 160 and g >= 160 and b >= 160 and max(r, g, b) - min(r, g, b) <= 18:
        return True
    return False


def flood_transparent(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited = [[False] * width for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= width or y >= height or visited[y][x]:
            continue
        visited[y][x] = True
        r, g, b, a = pixels[x, y]
        if not is_outer_background(r, g, b, a):
            continue
        pixels[x, y] = (r, g, b, 0)
        queue.extend([(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)])

    return rgba


def trim_transparent(img: Image.Image, padding: int = 8) -> Image.Image:
    rgba = img.convert("RGBA")
    bbox = rgba.getbbox()
    if not bbox:
        return rgba
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(rgba.width, right + padding)
    bottom = min(rgba.height, bottom + padding)
    return rgba.crop((left, top, right, bottom))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = ASSETS if ASSETS.exists() else SOURCE_COPY
    if not src.exists():
        raise FileNotFoundError(f"Logo source not found: {src}")

    img = Image.open(src)
    img.save(SOURCE_COPY)
    processed = trim_transparent(flood_transparent(img))
    processed.save(OUT, optimize=True)
    print(f"Saved {OUT} ({processed.size[0]}x{processed.size[1]})")


if __name__ == "__main__":
    main()
