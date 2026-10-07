"""One-off probe: can we reach Smyths homepage images via Playwright?"""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

URL = "https://www.smythstoys.com/uk/en-gb"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        try:
            resp = page.goto(URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(8000)
            print("status", resp.status if resp else None)
            print("title", page.title())
            html = page.content()
            print("html_len", len(html))
            blocked = "Incapsula" in html or "Request unsuccessful" in html
            print("blocked", blocked)
            pattern = r'https?://[^"\']+\.(?:jpg|jpeg|png|webp|gif|svg)(?:\?[^"\']*)?'
            imgs = sorted(set(re.findall(pattern, html, re.I)))
            print("img_count", len(imgs))
            for u in imgs[:30]:
                print(u)
        except Exception as exc:  # noqa: BLE001
            print("ERR", exc)
            return 1
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
