"""Read barcode / SKU text from label photos via OpenAI Vision (same env as ERP POS)."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from mobile_backend.services.barcode_lookup_service import lookup_queries

MAX_BYTES = 6 * 1024 * 1024

_LABEL_SYS_PROMPT = (
    "You read retail product label photos for a POS / warehouse app. "
    "Extract the machine-readable product code printed on the label. "
    "Output ONLY valid JSON: one object with keys "
    '"barcode" (string — EAN/UPC digits or internal shelf code as printed, no spaces), '
    '"item_code" (integer ERP SKU only if clearly printed separately), '
    '"item_name" (product title if visible). '
    "Prefer the EAN/UPC number printed under the barcode bars. "
    "For Code 39 text like *6906516124152* return barcode as 6906516124152 without asterisks. "
    "No markdown."
)


def openai_configured() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def _vision_model() -> str:
    return (os.environ.get("OPENAI_VISION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\s*", "", raw, count=1)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
        m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None
        if data is None:
            mobj = re.search(r"\{[\s\S]*\}", raw)
            if not mobj:
                raise
            data = json.loads(mobj.group(0))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("AI response is not JSON")
    return [row for row in data if isinstance(row, dict)]


def _fallback_from_text(text: str) -> list[dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return []
    collapsed = re.sub(r"[\s*\-]", "", t)
    if re.fullmatch(r"\d{8,14}", collapsed):
        return [{"barcode": collapsed, "qty": 1}]
    m = re.search(r"\b\d{8,14}\b", t)
    if m:
        return [{"barcode": m.group(0), "qty": 1}]
    return []


def _queries_from_ai_row(row: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    def add(val: Any) -> None:
        s = str(val or "").strip()
        if not s:
            return
        k = s.upper()
        if k in seen:
            return
        seen.add(k)
        ordered.append(s)

    for key in ("barcode", "manufacturer_id", "manufacturerid", "ean", "upc"):
        add(row.get(key))
    ic = row.get("item_code") if row.get("item_code") is not None else row.get("itemcode")
    if ic is not None:
        add(ic)
    for key in ("item_name", "itemname", "name", "product_name"):
        add(row.get(key))
    return ordered


def extract_ai_rows_from_image(image_bytes: bytes, *, mime: str = "image/jpeg") -> list[dict[str, Any]]:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured on the server (same key as ERP POS).")
    if not image_bytes or len(image_bytes) > MAX_BYTES:
        raise ValueError("Image missing or too large (max 6 MB).")

    mime = (mime or "image/jpeg").strip() or "image/jpeg"
    if not mime.startswith("image/"):
        mime = "image/jpeg"
    b64url = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime};base64,{b64url}"

    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=90.0)
    completion = client.chat.completions.create(
        model=_vision_model(),
        temperature=0.1,
        messages=[
            {"role": "system", "content": _LABEL_SYS_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Read the product barcode number and any visible SKU from this label photo. "
                            "Return one JSON object."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        max_tokens=800,
    )
    ai_text = (completion.choices[0].message.content or "").strip()
    try:
        rows = _parse_json_array(ai_text)
    except Exception:
        rows = _fallback_from_text(ai_text)
    if not rows:
        rows = _fallback_from_text(ai_text)
    return rows


def scan_label_and_lookup(
    image_bytes: bytes,
    *,
    mime: str = "image/jpeg",
    locationcode: int | None = None,
) -> dict[str, Any]:
    ai_rows = extract_ai_rows_from_image(image_bytes, mime=mime)
    all_queries: list[str] = []
    for row in ai_rows:
        all_queries.extend(_queries_from_ai_row(row))

    hit = lookup_queries(all_queries, locationcode=locationcode)
    primary_barcode = ""
    if hit:
        primary_barcode, _ = hit
    elif all_queries:
        primary_barcode = all_queries[0]

    return {
        "ai_rows": ai_rows,
        "queries_tried": all_queries,
        "barcode": primary_barcode,
        "matched": hit is not None,
        "item": hit[1] if hit else None,
        "query_used": hit[0] if hit else None,
    }


def decode_image_base64(image_base64: str) -> tuple[bytes, str]:
    raw_input = (image_base64 or "").strip()
    if not raw_input:
        raise ValueError("image_base64 is required")
    mime = "image/jpeg"
    if raw_input.startswith("data:"):
        head, _, body = raw_input.partition(",")
        mime = head.replace("data:", "").split(";")[0].strip() or mime
        raw_input = body
    try:
        raw = base64.b64decode(raw_input)
    except Exception as exc:
        raise ValueError("Invalid image_base64") from exc
    return raw, mime
