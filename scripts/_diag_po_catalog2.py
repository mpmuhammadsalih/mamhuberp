from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db import set_active_db_key
from nexa_http.session_wrap import session


def main() -> None:
    session.clear()
    session["user"] = "mobile"
    session["location_code"] = 28
    set_active_db_key(None)

    from addons.purchase.controllers import routes as p

    p._apply_db()
    print("loc", p._resolve_location_code())
    rows = p._get_items_with_alternate_uoms_filtered(search=None, limit=20, supplier_code=None)
    print("alt filtered", len(rows or []), (rows or [])[:3])
    rows2 = p._get_items_for_location_filtered(search=None, limit=20, supplier_code=None)
    print("loc filtered", len(rows2 or []), (rows2 or [])[:3])

    from mobile_backend.request_context import set_request_jwt_claims
    from starlette.requests import Request

    # Direct service call via erp scope needs JWT
    from mobile_backend import request_context as rc

    token = rc._jwt_claims.set({"sub": "mobile", "tenant_id": None, "loc_code": 28})
    try:
        from mobile_backend.services import purchase_order_service as pos

        items = pos.list_catalog_items(search="", limit=20, supplier_code="")
        print("service items", len(items), items[:2])
        items_s = pos.list_catalog_items(search="RICE", limit=20, supplier_code="10001")
        print("service search+sup", len(items_s), items_s[:2])
    finally:
        rc._jwt_claims.reset(token)


if __name__ == "__main__":
    main()
