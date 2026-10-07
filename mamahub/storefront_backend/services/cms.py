"""CMS pages for storefront."""

from __future__ import annotations



from typing import Any, Dict, List, Optional, Tuple



from addons.ecommerce import cms_db





def _ready() -> bool:

    return cms_db.cms_table_ready()





def list_pages() -> List[Dict[str, Any]]:

    if not _ready():

        return []

    cms_db.ensure_default_pages()

    pages, _ = cms_db.list_pages(published_only=True)

    return pages





def get_page(slug: str) -> Optional[Dict[str, Any]]:

    if not _ready():

        return None

    cms_db.ensure_default_pages()

    row = cms_db.get_page_by_slug(slug, published_only=True)

    return dict(row) if row else None





def submit_contact(payload: Dict[str, Any]) -> Tuple[bool, str]:

    cms_db.ensure_default_pages()

    return cms_db.create_contact_inquiry(payload)

