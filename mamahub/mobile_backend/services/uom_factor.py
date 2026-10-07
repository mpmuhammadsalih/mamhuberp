"""UOM conversion factor → stock base qty (ERP Item Master / ITEMALTERNATEUOMMAP).

Same rule as GRN / ERP ``_get_uom_factor_for_item``:
``stock_qty_base = qty × conversionfactor (+ bonus)``.
"""

from __future__ import annotations

from typing import Any


def _purchase_st() -> Any:
    from addons.purchase.controllers import routes as st

    return st


def _line_float(row: dict[str, Any], *keys: str) -> float:
    for k in keys:
        raw = row.get(k)
        if raw is None:
            raw = row.get(k.lower()) if isinstance(k, str) else None
        if raw is None and isinstance(k, str):
            raw = row.get(k.upper())
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def client_uom_factor(raw: dict[str, Any] | None) -> float:
    """Positive client-supplied factor, or 0 if absent/invalid."""
    if not raw:
        return 0.0
    f = _line_float(raw, "conversionfactor", "conversion_factor", "uomfactor", "factor")
    return f if f > 0 else 0.0


def resolve_uom_factor(
    item_code: Any,
    uom: str,
    raw: dict[str, Any] | None = None,
    *,
    st: Any | None = None,
) -> float:
    """
    Conversion factor to base stock UOM.

    Prefer ERP map. Client factor is used only when the map returns ~1 and
    the client sent a pack factor > 1 (map miss / stale client data).
    """
    helper = st or _purchase_st()
    factor = 1.0
    try:
        factor = float(helper._get_uom_factor_for_item(item_code, uom) or 1.0)
    except Exception:
        factor = 1.0
    if factor <= 0:
        factor = 1.0
    client = client_uom_factor(raw)
    if client > 0 and (factor <= 1.0 + 1e-12) and client > 1.0 + 1e-12:
        factor = client
    return factor


def stock_base_qty(qty: float, factor: float, bonus: float = 0.0) -> float:
    """Unsigned base stock qty (qty × factor + bonus)."""
    return round(abs(float(qty or 0)) * float(factor if factor > 0 else 1) + abs(float(bonus or 0)), 6)


def apply_line_stock_base(
    line: dict[str, Any],
    *,
    item_code: Any | None = None,
    uom: str | None = None,
    qty: float | None = None,
    bonus: float = 0.0,
    st: Any | None = None,
    signed: bool = False,
) -> float:
    """
    Set ``conversionfactor`` / ``conversion_factor`` / ``base_qty`` / ``baseqty`` on *line*.

    Returns base qty. If ``signed`` and line qty is negative, base_qty is negative
    (sales return after negate).
    """
    code = item_code
    if code is None:
        code = line.get("itemcode") or line.get("item_code")
    unit = (uom if uom is not None else str(line.get("uom") or line.get("unit") or "PCS")).strip() or "PCS"
    if qty is None:
        qty = _line_float(line, "quantity", "qty", "adjust_qty", "adjustqty", "transfer_qty")
    factor = resolve_uom_factor(code, unit, line, st=st)
    base = stock_base_qty(qty, factor, bonus)
    if signed and float(qty or 0) < 0:
        base = -base
    line["uom"] = unit
    line["conversionfactor"] = factor
    line["conversion_factor"] = factor
    line["uomfactor"] = factor
    line["factor"] = factor
    line["baseqty"] = base
    line["base_qty"] = base
    return base
