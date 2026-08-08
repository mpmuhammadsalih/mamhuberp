"""
Example domain model boundary for demo_sales.

In a large migration you might:
  - Delegate SQL to ``db.py`` repositories with explicit names per tenant table.
  - Keep pure DTO/dataclass types here so services stay testable without Oracle.

This file does **not** duplicate DB schema definitions (that stays centralized in ``db.py`` until ORM adoption).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class SaleOrderRow:
    """Thin row snapshot for templates/API (demo data shape)."""
    ref: str
    customer: str
    total: float
    state: str
    date: Optional[datetime] = None

def demo_orders_as_dicts() -> Dict[str, Any]:
    """
    Placeholder: replace with ``_fetch_rows`` / repository against real SO_HDR table.

    Keeps controllers thin: call ``services`` which calls models helpers.
    """
    return {'rows': [{'ref': 'SO-1001', 'customer': 'Acme', 'total': 1250.0, 'state': 'confirmed'}, {'ref': 'SO-1002', 'customer': 'Globex', 'total': 890.0, 'state': 'draft'}]}
