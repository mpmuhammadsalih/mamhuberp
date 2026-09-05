#!/usr/bin/env python3
"""Seed default CMS pages (FAQ, contact, terms, privacy) into MH_CMS_PAGE."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from addons.ecommerce import cms_db  # noqa: E402


def main() -> None:
    if not cms_db.cms_table_ready():
        print('MH_CMS_PAGE table is not ready. Run schema first.')
        sys.exit(1)
    cms_db.ensure_default_pages()
    pages, warning = cms_db.list_pages()
    if warning:
        print(warning)
    print(f'Seeded CMS pages: {len(pages)} total')
    for page in pages:
        print(f"  - {page['page_code']} -> /page/{page['slug']}")


if __name__ == '__main__':
    main()
