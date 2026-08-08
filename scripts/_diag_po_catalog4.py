from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from mobile_backend import request_context as rc


def main() -> None:
    # Simulate request-bound session like mobile API
    req = MagicMock()
    req.session = {}
    token_req = rc._current_request.set(req)
    token_jwt = rc._jwt_claims.set({"sub": "admin", "tenant_id": None, "loc_code": 28})
    try:
        from mobile_backend.services import purchase_order_service as pos

        items = pos.list_catalog_items(search="", limit=30, supplier_code="")
        print("empty search", len(items))
        if items:
            print("first", items[0])
        items2 = pos.list_catalog_items(search="", limit=30, supplier_code="10001")
        print("with supplier filter", len(items2))
        items3 = pos.list_catalog_items(search="RICE", limit=30, supplier_code="")
        print("search RICE", len(items3), items3[:1])
        print("session after", dict(req.session))
    finally:
        rc._jwt_claims.reset(token_jwt)
        rc._current_request.reset(token_req)


if __name__ == "__main__":
    main()
