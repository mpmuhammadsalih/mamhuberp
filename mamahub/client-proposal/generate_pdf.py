"""Regenerate client proposal PDF from HTML (A4, print-safe fonts)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "Nexus-ERP-Client-Proposal.html"
PDF = ROOT / "Nexus-ERP-Client-Proposal.pdf"


def main() -> None:
    if not HTML.is_file():
        raise SystemExit(f"Missing HTML: {HTML}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 794, "height": 1123})  # A4 at 96dpi
        page.goto(HTML.as_uri(), wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(
            path=str(PDF),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()

    print(f"PDF written: {PDF} ({PDF.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
