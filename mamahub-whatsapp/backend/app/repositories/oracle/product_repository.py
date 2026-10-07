"""Product search against Oracle ITEMMASTER (MamaHub ERP)."""
from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.utils.product_images import public_product_image_url


class OracleItemMasterProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.location_code = get_settings().oracle_location_code

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        location_code: Optional[int] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        in_stock: bool = False,
        offers: bool = False,
        collection: Optional[str] = None,
        age: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        loc = int(location_code or self.location_code)
        q = (query or "").strip()
        category = (category or "").strip() or None
        brand = (brand or "").strip() or None
        collection = (collection or "").strip().lower() or None
        age = (age or "").strip() or None
        if collection == "offers":
            offers = True
        if collection in {"new", "trending"} and not q:
            rows = self.list_new(limit=int(limit), location_code=loc) if collection == "new" else self.list_trending(limit=int(limit), location_code=loc)
            return self._apply_filters(self._restrict_age(rows, age), category, brand, in_stock, offers)
        if age and not q and not category and not brand and not offers:
            return self._apply_filters(self.list_by_age(age, limit=int(limit), location_code=loc), None, None, in_stock, False)
        if offers and not q and not category and not brand:
            return self._apply_filters(self._restrict_age(self.list_offers(limit=max(int(limit), 24)), age), None, None, in_stock, False)
        if not q and not category and not brand and not in_stock and not age:
            featured = self.list_new(limit=int(limit), location_code=loc)
            if featured:
                return featured
            return self.list_trending(limit=int(limit), location_code=loc)
        like = f"%{q.upper()}%" if q else "%"
        starts = f"{q.upper()}%" if q else "%"
        fetch_limit = int(limit) * 3 if (category or brand or in_stock or offers or age) else int(limit)
        rows = self._run_search(like, loc, fetch_limit, starts, category=category, brand=brand, in_stock=in_stock)
        mapped = self._apply_filters(self._restrict_age([self._map(row) for row in rows], age), category, brand, in_stock, offers)
        if mapped or location_code == 0:
            return mapped[: int(limit)]
        rows = self._run_search(like, None, fetch_limit, starts, category=category, brand=brand, in_stock=in_stock)
        return self._apply_filters(self._restrict_age([self._map(row) for row in rows], age), category, brand, in_stock, offers)[: int(limit)]

    def list_filters(self, *, location_code: Optional[int] = None) -> dict[str, Any]:
        loc = int(location_code or self.location_code)
        return {
            "categories": self._category_names(loc),
            "ages": self._age_groups(),
        }

    def _category_names(self, loc: int) -> list[str]:
        queries = [
            """
            SELECT DISTINCT TRIM(c.NAME) AS name
            FROM CATEGORY c
            JOIN ITEMMASTER im
              ON im.LOCATIONCODE = c.LOCATIONCODE
             AND im.CATEGORYCODE = c.CODE
            WHERE c.LOCATIONCODE = :loc
              AND c.NAME IS NOT NULL
            ORDER BY name
            FETCH FIRST 80 ROWS ONLY
            """,
            """
            SELECT DISTINCT TRIM(TO_CHAR(im.CATEGORYCODE)) AS name
            FROM ITEMMASTER im
            WHERE im.LOCATIONCODE = :loc
              AND im.CATEGORYCODE IS NOT NULL
            ORDER BY name
            FETCH FIRST 80 ROWS ONLY
            """,
        ]
        for sql in queries:
            try:
                rows = self.session.execute(text(sql), {"loc": loc}).all()
                return [str(row[0]) for row in rows if str(row[0] or "").strip()]
            except Exception:
                self.session.rollback()
        return []

    def _age_groups(self) -> list[dict[str, str]]:
        try:
            rows = self.session.execute(
                text(
                    """
                    SELECT TRIM(SLUG) AS slug, TRIM(AGE_GROUP_NAME) AS name
                    FROM MH_AGE_GROUP
                    WHERE IS_ACTIVE = 1
                    ORDER BY SORT_ORDER, AGE_GROUP_NAME
                    """
                )
            ).mappings().all()
            return [{"slug": str(row["slug"]), "name": str(row["name"])} for row in rows if row.get("slug") and row.get("name")]
        except Exception:
            self.session.rollback()
            return []

    def _age_item_codes(self, age: str) -> list[str]:
        try:
            rows = self.session.execute(
                text(
                    """
                    SELECT DISTINCT TO_CHAR(iag.ITEM_CODE) AS itemcode
                    FROM MH_ITEM_AGE_GROUP iag
                    JOIN MH_AGE_GROUP ag ON ag.AGE_GROUP_ID = iag.AGE_GROUP_ID
                    WHERE ag.IS_ACTIVE = 1
                      AND (LOWER(ag.SLUG) = :age OR LOWER(ag.AGE_GROUP_CODE) = :age)
                    """
                ),
                {"age": age.lower()},
            ).all()
            return [str(row[0]) for row in rows if row[0]]
        except Exception:
            self.session.rollback()
            return []

    def _restrict_age(self, rows: List[dict[str, Any]], age: Optional[str]) -> List[dict[str, Any]]:
        if not age:
            return rows
        allowed = set(self._age_item_codes(age))
        if not allowed:
            return []
        return [item for item in rows if str(item.get("itemcode") or "") in allowed]

    def list_by_age(self, age: str, *, limit: int = 36, location_code: Optional[int] = None) -> List[dict[str, Any]]:
        loc = int(location_code or self.location_code)
        return self._mapped_by_codes(self._age_item_codes(age)[: max(int(limit), 36)], loc)[: int(limit)]

    def list_new(self, *, limit: int = 36, location_code: Optional[int] = None) -> List[dict[str, Any]]:
        loc = int(location_code or self.location_code)
        try:
            rows = self.session.execute(
                text(
                    f"""
                    SELECT * FROM (
                        SELECT
                            TO_CHAR(im.ITEMCODE) AS itemcode,
                            im.ITEMNAME AS itemname,
                            NULL AS barcode,
                            NULL AS brand,
                            c.NAME AS category,
                            NVL(im.COSTPRICE, 0) AS costprice,
                            NVL(im.RETAILPRICE, 0) AS retailprice,
                            NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                            NVL(im.CURRENTSTOCK, 0) AS currentstock,
                            im.IMAGE_PATH AS image_url,
                            'Y' AS flag
                        FROM ITEMMASTER im
                        LEFT JOIN CATEGORY c
                          ON c.LOCATIONCODE = im.LOCATIONCODE
                         AND c.CODE = im.CATEGORYCODE
                        WHERE im.LOCATIONCODE = :loc
                          AND NVL(im.CURRENTSTOCK, 0) > 0
                        ORDER BY im.ITEMCODE DESC
                    ) WHERE ROWNUM <= :lim
                    """
                ),
                {"loc": loc, "lim": int(limit)},
            ).mappings().all()
            return [self._map(row) for row in rows]
        except Exception:
            self.session.rollback()
            return []

    def list_trending(self, *, limit: int = 36, location_code: Optional[int] = None) -> List[dict[str, Any]]:
        loc = int(location_code or self.location_code)
        codes: list[str] = []
        try:
            rows = self.session.execute(
                text(
                    """
                    SELECT TO_CHAR(item_code) AS itemcode FROM (
                        SELECT oi.ITEM_CODE AS item_code, SUM(NVL(oi.QUANTITY, 0)) AS units_sold
                        FROM MH_ORDER_ITEM oi
                        GROUP BY oi.ITEM_CODE
                        ORDER BY units_sold DESC
                    ) WHERE ROWNUM <= :lim
                    """
                ),
                {"lim": int(limit)},
            ).all()
            codes = [str(row[0]) for row in rows if row[0]]
        except Exception:
            self.session.rollback()
        if codes:
            mapped = self._mapped_by_codes(codes, loc)
            if mapped:
                return mapped[: int(limit)]
        return self.list_new(limit=limit, location_code=loc)

    def _mapped_by_codes(self, codes: List[str], loc: int) -> List[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for code in codes:
            item = self.get_by_code(code, location_code=loc)
            if item and item.get("itemcode"):
                found[str(item["itemcode"])] = item
        return [found[code] for code in codes if code in found]

    def _apply_filters(
        self,
        rows: List[dict[str, Any]],
        category: Optional[str],
        brand: Optional[str],
        in_stock: bool,
        offers: bool,
    ) -> List[dict[str, Any]]:
        cat = (category or "").strip().lower()
        brd = (brand or "").strip().lower()
        out: List[dict[str, Any]] = []
        for item in rows:
            if cat and str(item.get("category") or "").strip().lower() != cat:
                continue
            if brd and str(item.get("brand") or "").strip().lower() != brd:
                continue
            if in_stock and float(item.get("currentstock") or 0) <= 0:
                continue
            if offers and not item.get("offer_price"):
                continue
            out.append(item)
        return out

    def _run_search(
        self,
        like: str,
        loc: Optional[int],
        limit: int,
        starts: str,
        *,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        in_stock: bool = False,
    ):
        where_loc = "1=1" if loc is None else "im.LOCATIONCODE = :loc"
        params: dict[str, Any] = {"like": like, "lim": limit, "starts": starts}
        extra = ""
        if loc is not None:
            params["loc"] = loc
        if category:
            extra += " AND UPPER(NVL(c.NAME, TO_CHAR(im.CATEGORYCODE))) = :category"
            params["category"] = category.upper()
        if brand:
            extra += " AND UPPER(TO_CHAR(im.BRANDCODE)) = :brand"
            params["brand"] = brand.upper()
        if in_stock:
            extra += " AND NVL(im.CURRENTSTOCK, 0) > 0"
        queries = [
            f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    NULL AS barcode,
                    NULL AS brand,
                    c.NAME AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    im.IMAGE_PATH AS image_url,
                    'Y' AS flag
                FROM ITEMMASTER im
                LEFT JOIN CATEGORY c
                  ON c.LOCATIONCODE = im.LOCATIONCODE
                 AND c.CODE = im.CATEGORYCODE
                WHERE {where_loc}
                  AND (
                        :like = '%'
                     OR UPPER(im.ITEMNAME) LIKE :like
                     OR TO_CHAR(im.ITEMCODE) LIKE :like
                     OR UPPER(NVL(c.NAME, ' ')) LIKE :like
                  )
                  {extra}
                ORDER BY
                    CASE WHEN UPPER(im.ITEMNAME) LIKE :starts THEN 0 ELSE 1 END,
                    im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """,
            f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    TO_CHAR(im.BARCODE) AS barcode,
                    NVL(im.BRANDNAME, TO_CHAR(im.BRANDCODE)) AS brand,
                    NVL(im.CATEGORYNAME, TO_CHAR(im.CATEGORYCODE)) AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    im.IMAGE_PATH AS image_url,
                    NVL(im.FLAG, 'Y') AS flag
                FROM ITEMMASTER im
                WHERE {where_loc}
                  AND (
                        :like = '%'
                     OR UPPER(im.ITEMNAME) LIKE :like
                     OR TO_CHAR(im.ITEMCODE) LIKE :like
                     OR UPPER(NVL(TO_CHAR(im.BARCODE), ' ')) LIKE :like
                     OR UPPER(NVL(im.BRANDNAME, ' ')) LIKE :like
                     OR UPPER(NVL(im.CATEGORYNAME, ' ')) LIKE :like
                  )
                ORDER BY
                    CASE WHEN UPPER(im.ITEMNAME) LIKE :starts THEN 0 ELSE 1 END,
                    im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """,
            f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    NULL AS barcode,
                    NVL(im.BRANDNAME, TO_CHAR(im.BRANDCODE)) AS brand,
                    NVL(im.CATEGORYNAME, TO_CHAR(im.CATEGORYCODE)) AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    im.IMAGE_PATH AS image_url,
                    'Y' AS flag
                FROM ITEMMASTER im
                WHERE {where_loc}
                  AND (
                        :like = '%'
                     OR UPPER(im.ITEMNAME) LIKE :like
                     OR TO_CHAR(im.ITEMCODE) LIKE :like
                     OR UPPER(NVL(im.BRANDNAME, ' ')) LIKE :like
                     OR UPPER(NVL(im.CATEGORYNAME, ' ')) LIKE :like
                  )
                ORDER BY
                    CASE WHEN UPPER(im.ITEMNAME) LIKE :starts THEN 0 ELSE 1 END,
                    im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """,
            f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    TO_CHAR(im.BARCODE) AS barcode,
                    TO_CHAR(im.BRANDCODE) AS brand,
                    TO_CHAR(im.CATEGORYCODE) AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    im.IMAGE_PATH AS image_url,
                    NVL(im.FLAG, 'Y') AS flag
                FROM ITEMMASTER im
                WHERE {where_loc}
                  AND (
                        UPPER(im.ITEMNAME) LIKE :like
                     OR TO_CHAR(im.ITEMCODE) LIKE :like
                     OR UPPER(NVL(TO_CHAR(im.BARCODE), ' ')) LIKE :like
                  )
                ORDER BY im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """,
            f"""
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    NULL AS barcode,
                    NULL AS brand,
                    NULL AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    NULL AS image_url,
                    'Y' AS flag
                FROM ITEMMASTER im
                WHERE {where_loc}
                  AND (
                        UPPER(im.ITEMNAME) LIKE :like
                     OR TO_CHAR(im.ITEMCODE) LIKE :like
                  )
                ORDER BY im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """,
        ]
        last_error: Exception | None = None
        for sql in queries:
            try:
                return self.session.execute(text(sql), params).mappings().all()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.session.rollback()
        if last_error:
            raise last_error
        return []

    def list_offers(self, *, limit: int = 9, location_code: Optional[int] = None) -> List[dict[str, Any]]:
        """Website Offers & deals: MH_MEDIA offer_price or WHOLESALEPRICE below retail."""
        loc = int(location_code or self.location_code)
        meta_offers = self._media_offer_prices()
        wholesale_rows = self._offer_item_rows(loc, int(limit) * 3)
        wanted = {str(code) for code in meta_offers}
        wanted.update(str(row.get("itemcode") or "") for row in wholesale_rows)
        wanted.discard("")
        by_code: dict[str, dict[str, Any]] = {}
        for row in wholesale_rows:
            code = str(row.get("itemcode") or "")
            if code:
                by_code[code] = row
        missing = [code for code in wanted if code not in by_code]
        for row in self._items_by_codes(missing, loc):
            code = str(row.get("itemcode") or "")
            if code:
                by_code[code] = row
        mapped: List[dict[str, Any]] = []
        for code, row in by_code.items():
            item = self._map(row)
            meta_price = meta_offers.get(code)
            if meta_price and meta_price < float(item.get("retailprice") or 0):
                item["offer_price"] = meta_price
            if item.get("offer_price"):
                mapped.append(item)
        mapped.sort(key=lambda item: float(item.get("retailprice") or 0) - float(item.get("offer_price") or 0), reverse=True)
        return mapped[: int(limit)]

    def _media_offer_prices(self) -> dict[str, float]:
        try:
            rows = self.session.execute(
                text(
                    """
                    SELECT REF_KEY AS ref_key, META_JSON AS meta_json
                    FROM MH_MEDIA
                    WHERE PLACEMENT = 'product_detail'
                      AND META_JSON LIKE '%offer_price%'
                    """
                )
            ).mappings().all()
        except Exception:
            self.session.rollback()
            return {}
        offers: dict[str, float] = {}
        for row in rows:
            raw = row.get("meta_json") or ""
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            try:
                price = float(data.get("offer_price") or 0)
            except (TypeError, ValueError):
                continue
            code = str(row.get("ref_key") or "").strip()
            if code and price > 0:
                offers[code] = price
        return offers

    def _offer_item_rows(self, loc: int, limit: int) -> list[Any]:
        sql = text(
            """
            SELECT * FROM (
                SELECT
                    TO_CHAR(im.ITEMCODE) AS itemcode,
                    im.ITEMNAME AS itemname,
                    NULL AS barcode,
                    NULL AS brand,
                    NULL AS category,
                    NVL(im.COSTPRICE, 0) AS costprice,
                    NVL(im.RETAILPRICE, 0) AS retailprice,
                    NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                    NVL(im.CURRENTSTOCK, 0) AS currentstock,
                    im.IMAGE_PATH AS image_url,
                    'Y' AS flag
                FROM ITEMMASTER im
                WHERE im.LOCATIONCODE = :loc
                  AND NVL(im.WHOLESALEPRICE, 0) > 0
                  AND NVL(im.RETAILPRICE, 0) > 0
                  AND NVL(im.WHOLESALEPRICE, 0) < NVL(im.RETAILPRICE, 0)
                ORDER BY (NVL(im.RETAILPRICE, 0) - NVL(im.WHOLESALEPRICE, 0)) DESC, im.ITEMNAME
            ) WHERE ROWNUM <= :lim
            """
        )
        try:
            return list(self.session.execute(sql, {"loc": loc, "lim": int(limit)}).mappings().all())
        except Exception:
            self.session.rollback()
            return []

    def _items_by_codes(self, codes: List[str], loc: int) -> list[Any]:
        rows: list[Any] = []
        for code in codes[:40]:
            item = self.get_by_code(code, location_code=loc)
            if item:
                # get_by_code already mapped; stash as raw-like via reverse later
                rows.append(
                    {
                        "itemcode": item["itemcode"],
                        "itemname": item["itemname"],
                        "barcode": item.get("barcode"),
                        "brand": item.get("brand"),
                        "category": item.get("category"),
                        "costprice": item.get("costprice") or 0,
                        "retailprice": item.get("retailprice") or 0,
                        "wholesaleprice": item.get("wholesaleprice") or 0,
                        "currentstock": item.get("currentstock") or 0,
                        "image_url": item.get("image_url"),
                        "flag": "Y" if item.get("active", True) else "N",
                    }
                )
        return rows

    def gallery_image_url(self, itemcode: str) -> Optional[str]:
        code = str(itemcode or "").strip()
        if not code:
            return None
        try:
            raw = self.session.execute(
                text(
                    """
                    SELECT IMAGE_URL FROM MH_MEDIA
                    WHERE IS_ACTIVE = 1
                      AND PLACEMENT IN ('product', 'product_detail')
                      AND REF_KEY = :code
                      AND IMAGE_URL NOT LIKE '%placeholder%'
                      AND IMAGE_URL NOT LIKE '%mamahub-logo%'
                    ORDER BY SORT_ORDER, MEDIA_ID
                    FETCH FIRST 1 ROWS ONLY
                    """
                ),
                {"code": code},
            ).scalar()
        except Exception:
            self.session.rollback()
            return None
        return public_product_image_url(raw, get_settings().storefront_base_url)

    def get_by_code(self, itemcode: str, *, location_code: Optional[int] = None) -> Optional[dict[str, Any]]:
        loc = int(location_code or self.location_code)
        sql = text(
            """
            SELECT
                TO_CHAR(im.ITEMCODE) AS itemcode,
                im.ITEMNAME AS itemname,
                NULL AS barcode,
                NULL AS brand,
                NULL AS category,
                NVL(im.COSTPRICE, 0) AS costprice,
                NVL(im.RETAILPRICE, 0) AS retailprice,
                NVL(im.WHOLESALEPRICE, 0) AS wholesaleprice,
                NVL(im.CURRENTSTOCK, 0) AS currentstock,
                im.IMAGE_PATH AS image_url,
                'Y' AS flag
            FROM ITEMMASTER im
            WHERE im.LOCATIONCODE = :loc AND TO_CHAR(im.ITEMCODE) = :code
            """
        )
        try:
            row = self.session.execute(sql, {"loc": loc, "code": str(itemcode)}).mappings().first()
        except Exception:
            self.session.rollback()
            return None
        return self._map(row) if row else None

    def _map(self, row: Any) -> dict[str, Any]:
        flag = str(row.get("flag") or "Y").upper()
        return {
            "itemcode": str(row.get("itemcode") or ""),
            "itemname": str(row.get("itemname") or ""),
            "barcode": str(row.get("barcode") or "") or None,
            "brand": str(row.get("brand") or "") or None,
            "category": str(row.get("category") or "") or None,
            "costprice": float(row.get("costprice") or 0),
            "retailprice": float(row.get("retailprice") or 0),
            "wholesaleprice": float(row.get("wholesaleprice") or 0),
            "offer_price": (
                float(row.get("wholesaleprice") or 0)
                if float(row.get("wholesaleprice") or 0) > 0
                and float(row.get("retailprice") or 0) > 0
                and float(row.get("wholesaleprice") or 0) < float(row.get("retailprice") or 0)
                else None
            ),
            "currentstock": float(row.get("currentstock") or 0),
            "image_url": public_product_image_url(row.get("image_url"), get_settings().storefront_base_url),
            "active": flag not in ("N", "0"),
            "currency": "QAR",
        }
