"""Arabic translation helpers for ecommerce product content."""
from __future__ import annotations

from typing import Tuple


def translate_to_arabic(text: str, *, context: str = 'product') -> Tuple[str, str]:
    """Return (arabic_text, source) using itemmaster AI/fallback when available."""
    src = str(text or '').strip()
    if not src:
        return ('', 'empty')
    try:
        from addons.itemmaster.controllers.routes import _translate_text_to_arabic

        return _translate_text_to_arabic(src, context=context)
    except Exception:
        return ('', 'none')
