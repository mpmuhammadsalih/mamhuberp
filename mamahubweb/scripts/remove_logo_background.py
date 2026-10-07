"""Remove outer black background from MamaHub logo PNG."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

SRC = Path(__file__).resolve().parents[1] / "frontend" / "public" / "images" / "mamahub-logo.png"
BACKUP = SRC.with_name("mamahub-logo-original.png")

# Pixels darker than this (and connected to image edge) become transparent.
DARK_THRESHOLD = 48


def is_background(r: int, g: int, b: int) -> bool:
    return r <= DARK_THRESHOLD and g <= DARK_THRESHOLD and b <= DARK_THRESHOLD


def remove_edge_black(path: Path) -> None:
    img = Image.open(path).convert("RGBA")
    width, height = img.size
    pixels = img.load()
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
        if a == 0 or not is_background(r, g, b):
            continue
        pixels[x, y] = (r, g, b, 0)
        queue.extend([(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)])

    if not BACKUP.exists():
        Image.open(path).save(BACKUP)

    img.save(path, optimize=True)
    print(f"Saved transparent logo to {path}")


if __name__ == "__main__":
    remove_edge_black(SRC)
