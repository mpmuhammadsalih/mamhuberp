"""GS1-style variable-weight (in-store) barcode parsing for POS."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Prefix 20–29 = variable measure; second digit = decimal places in weight field.
_VARIABLE_WEIGHT_PREFIX_RE = re.compile(r'^2[0-9]\d{11}$')


def ean13_check_digit(digits12: str) -> int:
    """EAN-13 check digit for the first 12 digits."""
    total = 0
    for i, ch in enumerate(digits12):
        n = int(ch)
        total += n * (1 if i % 2 == 0 else 3)
    return (10 - (total % 10)) % 10


def parse_variable_weight_barcode(raw: str) -> Optional[Dict[str, Any]]:
    """
    Parse a 13-digit variable-weight barcode (prefix 20–29).

    Layout: PP + CCCCC + WWWWW + D
      PP    = prefix (20–29); decimal places = int(PP[1])
      CCCCC = scale PLU (maps to ITEMMASTER.MANUFACTURERID, or ITEMCODE as fallback)
      WWWWW = weight value (integer, scaled by decimal places → kg)
      D     = EAN-13 check digit

    Returns None when the scan is not a 13-digit variable-weight barcode format.
    """
    code = re.sub(r'\D', '', str(raw or '').strip())
    if len(code) != 13 or not _VARIABLE_WEIGHT_PREFIX_RE.match(code):
        return None
    prefix = code[0:2]
    plu_raw = code[2:7]
    weight_raw = code[7:12]
    check_digit = int(code[12])
    decimal_places = int(prefix[1])
    try:
        plu_item_code = int(plu_raw)
    except ValueError:
        plu_item_code = 0
    if plu_item_code <= 0:
        return {
            'is_variable_weight_format': True,
            'valid': False,
            'error': 'Invalid variable-weight barcode: PLU is zero.',
            'raw': code,
            'plu': plu_raw,
        }
    expected_check = ean13_check_digit(code[:12])
    if check_digit != expected_check:
        return {
            'is_variable_weight_format': True,
            'valid': False,
            'error': 'Invalid variable-weight barcode: check digit does not match.',
            'raw': code,
            'plu': plu_raw,
            'plu_item_code': plu_item_code,
        }
    divisor = 10 ** decimal_places if decimal_places >= 0 else 1
    weight_kg = int(weight_raw) / float(divisor)
    if weight_kg <= 0:
        return {
            'is_variable_weight_format': True,
            'valid': False,
            'error': 'Invalid variable-weight barcode: weight must be greater than zero.',
            'raw': code,
            'plu': plu_raw,
            'plu_item_code': plu_item_code,
        }
    return {
        'is_variable_weight_format': True,
        'valid': True,
        'raw': code,
        'prefix': prefix,
        'plu': plu_raw,
        'plu_item_code': plu_item_code,
        'weight_kg': round(weight_kg, 6),
        'decimal_places': decimal_places,
    }
