"""Blueprint static URL prefixes (``url_for('addon.static', filename=...)``)."""
from __future__ import annotations

from typing import Dict, Optional

_BLUEPRINT_STATIC_BASE: Dict[str, str] = {}


def register_blueprint_static(blueprint_name: str, url_prefix: str) -> None:
    """Record the public base path for an addon's mounted static files (e.g. ``/demo-sales/static``)."""
    _BLUEPRINT_STATIC_BASE[blueprint_name] = url_prefix


def blueprint_static_base(blueprint_name: str) -> Optional[str]:
    return _BLUEPRINT_STATIC_BASE.get(blueprint_name)
