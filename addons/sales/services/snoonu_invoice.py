"""Import a Snoonu invoice into Sales Invoice: customer by mobile + lines."""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _detect_table,
    _get_connection,
    _get_table_columns,
    _safe_rows,
    _sales_orderno_find_billno,
    _table_exists,
    get_customer_loyalty_for_picker,
    get_customers_master_list,
    get_location_info_by_dbkey,
    insert_customer_loyalty_row,
)
from nexa_http import session
from storefront_backend.services.erp_customer import validate_mobile


def _location_code() -> int:
    raw = session.get('location_code')
    try:
        if raw is not None and str(raw).isdigit():
            return int(raw)
    except Exception:
        pass
    try:
        info = get_location_info_by_dbkey(None) or {}
        return int(info.get('locationcode') or 1)
    except Exception:
        return 1


_SNOONU_SYS = (
    'You read Snoonu (Qatar) merchant invoices, order tickets, and delivery receipts. '
    'Extract one JSON object only, no markdown:\n'
    '{'
    '"order_no": "Snoonu order / invoice number",'
    '"customer_name": "customer name as printed",'
    '"customer_name_en": "same person in English letters",'
    '"mobile": "Qatar mobile, digits or +974…",'
    '"address": "delivery address if printed",'
    '"bill_date": "YYYY-MM-DD invoice / order date",'
    '"delivery_date": "YYYY-MM-DD delivery date, same as bill_date if only one date is printed",'
    '"currency": "QAR",'
    '"lines": ['
    '{"item_name": "product name", "barcode": "full barcode/SKU/EAN digits", '
    '"qty": 1, "unit_price": 0, "amount": 0, '
    '"gift_wrap_name": "", "gift_wrap_amount": 0}'
    '],'
    '"delivery_fee": 0,'
    '"total": 0'
    '}\n'
    'Identify each product line by the BARCODE / SKU / EAN / GTIN printed on that line. '
    'Copy the full barcode into "barcode" with no spaces (keep a trailing -1 if printed). '
    'Do not invent barcodes. If a line has no barcode, set barcode to "". '
    'Gift wrapping is PER PRODUCT, printed under that item (e.g. '
    '"Gift Wrapping: Premium Gift Wrap for Girls" with its own amount). '
    'Put it on THAT product as gift_wrap_name + gift_wrap_amount. Leave both empty when that item has no wrap. '
    'Do not emit gift wrap as a separate top-level line. Do not copy one wrap onto every item. '
    'Product amount is the printed product total (often includes wrap). Do not subtract wrap in the JSON. '
    'Snoonu PDFs print ONE price per line: that number is the LINE TOTAL (amount), not the unit price. '
    'Always set amount to the printed line total. Always set unit_price = amount / qty. '
    'Never copy the printed total into unit_price when qty is greater than 1. '
    'qty default 1 when missing. Skip payment-method lines, promo banners, and driver tips. '
    'If the customer name is Arabic, set customer_name_en to the common English spelling '
    '(e.g. محمد علي → Mohammed Ali). If already English, copy it to customer_name_en. '
    'Never put Arabic letters in customer_name_en. '
    'Extract bill_date from the invoice / order date. If delivery date is printed, use it; '
    'otherwise set delivery_date equal to bill_date. Always return dates as YYYY-MM-DD.'
)

_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')
_AR_TO_LATIN = {
    'ا': 'A', 'أ': 'A', 'إ': 'I', 'آ': 'A', 'ء': '', 'ؤ': 'U', 'ئ': 'I',
    'ب': 'B', 'ت': 'T', 'ث': 'TH', 'ج': 'J', 'ح': 'H', 'خ': 'KH',
    'د': 'D', 'ذ': 'DH', 'ر': 'R', 'ز': 'Z', 'س': 'S', 'ش': 'SH',
    'ص': 'S', 'ض': 'D', 'ط': 'T', 'ظ': 'Z', 'ع': 'A', 'غ': 'GH',
    'ف': 'F', 'ق': 'Q', 'ك': 'K', 'ل': 'L', 'م': 'M', 'ن': 'N',
    'ه': 'H', 'ة': 'A', 'و': 'W', 'ي': 'Y', 'ى': 'A',
    'ً': '', 'ٌ': '', 'ٍ': '', 'َ': '', 'ُ': '', 'ِ': '', 'ّ': '', 'ْ': '', 'ـ': '',
}


def _has_arabic(text: str) -> bool:
    return bool(text and _ARABIC_RE.search(text))


def _transliterate_arabic(text: str) -> str:
    out = []
    for ch in str(text or ''):
        if ch in _AR_TO_LATIN:
            out.append(_AR_TO_LATIN[ch])
        elif not _ARABIC_RE.match(ch):
            out.append(ch)
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def _openai_name_to_english(name: str) -> str:
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key or not name.strip():
        return ''
    try:
        from openai import OpenAI

        model = (os.environ.get('OPENAI_VISION_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
        client = OpenAI(api_key=api_key, timeout=30.0)
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=40,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Transliterate a Qatar person name into common English spelling. '
                        'Return only the name in Latin letters. No Arabic. No quotes.'
                    ),
                },
                {'role': 'user', 'content': name.strip()[:80]},
            ],
        )
        return (completion.choices[0].message.content or '').strip().strip('"\'')
    except Exception:
        return ''


def _english_customer_name(extracted: Dict[str, Any]) -> str:
    en = str(extracted.get('customer_name_en') or extracted.get('customer_name_english') or '').strip()
    raw = str(extracted.get('customer_name') or extracted.get('name') or '').strip()
    if en and not _has_arabic(en):
        return en.upper()[:40]
    src = en or raw
    if not src:
        return ''
    if not _has_arabic(src):
        return src.upper()[:40]
    converted = _openai_name_to_english(src)
    if converted and not _has_arabic(converted):
        return converted.upper()[:40]
    fallback = _transliterate_arabic(src)
    return (fallback or src).upper()[:40]


def _update_loyalty_name(location_code: int, code: Any, english_name: str) -> None:
    if not english_name or not _table_exists('CUSTOMERLOYALTY'):
        return
    try:
        cc = int(code)
    except (TypeError, ValueError):
        return
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE CUSTOMERLOYALTY
                    SET CUSTOMERNAME = :n
                    WHERE LOCATIONCODE = :loc AND CUSTOMERCODE = :cc
                    """,
                    {'n': english_name[:40], 'loc': int(location_code), 'cc': cc},
                )
            conn.commit()
    except Exception:
        pass


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return default
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return default


def _normalize_iso_date(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw or raw.lower() in ('none', 'null', 'n/a', '-'):
        return ''
    raw = raw.replace('.', '/').replace('\\', '/')
    iso = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', raw)
    if iso:
        y, mo, d = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f'{y:04d}-{mo:02d}-{d:02d}'
    dmy = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', raw)
    if dmy:
        d, mo, y = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        if mo > 12 and d <= 12:
            d, mo = mo, d
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f'{y:04d}-{mo:02d}-{d:02d}'
    from datetime import datetime

    for fmt in ('%d %b %Y', '%d %B %Y', '%d-%b-%Y', '%d-%B-%Y', '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y'):
        try:
            return datetime.strptime(raw[:24], fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


def _invoice_dates(extracted: Dict[str, Any]) -> Tuple[str, str]:
    bill = _normalize_iso_date(
        extracted.get('bill_date')
        or extracted.get('invoice_date')
        or extracted.get('order_date')
        or extracted.get('date')
    )
    delivery = _normalize_iso_date(extracted.get('delivery_date') or extracted.get('delivered_date'))
    iso = bill or delivery
    return iso, iso


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
        raw = re.sub(r'\s*```$', '', raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {'lines': data}
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError('Could not parse Snoonu invoice JSON.')


def _customer_payload(location_code: int, code: Any, created: bool, fallback_name: str = 'SNOONU') -> Dict[str, Any]:
    rows = get_customers_master_list(for_picker=True, picker_search=str(code or ''), picker_limit=20)
    hit = None
    for row in rows or []:
        if str(row.get('code') or row.get('CODE') or '').strip() == str(code).strip():
            hit = row
            break
    if not hit and rows:
        hit = rows[0]
    hit = hit or {}
    return {
        'code': str(hit.get('code') or hit.get('CODE') or code or ''),
        'name': str(hit.get('name') or hit.get('NAME') or fallback_name),
        'phone': str(hit.get('phone') or hit.get('PHONE') or ''),
        'address': str(hit.get('address') or hit.get('ADDRESS') or ''),
        'billing_type': str(hit.get('customer_billing_type') or hit.get('CUSTOMER_BILLING_TYPE') or 'CREDIT'),
        'credit_limit': hit.get('creditlimit') or hit.get('CREDITLIMIT') or 0,
        'created': created,
        'location_code': int(location_code),
    }


def _find_customer_named_snoonu(location_code: int) -> Optional[Dict[str, Any]]:
    if not _table_exists('CUSTOMER'):
        return None
    loc = int(location_code)
    rows = _safe_rows(
        """
        SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername
        FROM CUSTOMER
        WHERE LOCATIONCODE = :loc
          AND UPPER(TRIM(CUSTOMERNAME)) = 'SNOONU'
        FETCH FIRST 1 ROWS ONLY
        """,
        {'loc': loc},
    )
    if rows:
        return rows[0]
    rows = _safe_rows(
        """
        SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername
        FROM CUSTOMER
        WHERE LOCATIONCODE = :loc
          AND UPPER(TRIM(CUSTOMERNAME)) LIKE 'SNOONU%'
        ORDER BY CUSTOMERCODE
        FETCH FIRST 1 ROWS ONLY
        """,
        {'loc': loc},
    )
    return rows[0] if rows else None


def _ensure_snoonu_credit_billing(location_code: int, customer_code: Any) -> None:
    """Snoonu is a marketplace account — invoices must be Credit, not Cash."""
    try:
        cc = int(customer_code)
    except (TypeError, ValueError):
        return
    cols = {str(c).upper() for c in (_get_table_columns('CUSTOMER') or [])}
    if 'CUSTOMER_BILLING_TYPE' not in cols:
        return
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE CUSTOMER
                    SET CUSTOMER_BILLING_TYPE = 'CREDIT'
                    WHERE LOCATIONCODE = :loc
                      AND CUSTOMERCODE = :cc
                      AND UPPER(TRIM(NVL(CUSTOMER_BILLING_TYPE, 'CASH'))) <> 'CREDIT'
                    """,
                    {'loc': int(location_code), 'cc': cc},
                )
            conn.commit()
    except Exception:
        pass


def _create_snoonu_bill_customer(location_code: int) -> Optional[Dict[str, Any]]:
    if not _table_exists('CUSTOMER'):
        return None
    cols = {str(c).upper() for c in (_get_table_columns('CUSTOMER') or [])}
    loc = int(location_code)
    nxt = _safe_rows(
        'SELECT NVL(MAX(CUSTOMERCODE), 0) + 1 AS n FROM CUSTOMER WHERE LOCATIONCODE = :loc',
        {'loc': loc},
    )
    code = int((nxt[0] or {}).get('n') or 1)
    if code == 90001:
        code = 90002
    row = {
        'LOCATIONCODE': loc,
        'CUSTOMERCODE': code,
        'CUSTOMERNAME': 'SNOONU',
        'CREDITLIMIT': 0,
        'CREDITTERMS': 0,
        'SALESMANCODE': 0,
        'FLAG': 'Y',
        'CUSTOMERCATEGORY': 0,
        'BYSALESMAN': 0,
        'ROUTENO': 0,
        'CREATEDSTATUS': 'N',
        'TRANSFERBRANCH': 'N',
        'PRINTSEPRATE': 'N',
        'QID': 0,
        'ACTIVE': 'Y',
        'COUNTERSALE': 'Y',
        'DUEDAYS': 0,
        'MAINGROUP': 0,
        'CUSTOMER_BILLING_TYPE': 'CREDIT',
        'SOURCE_CHANNEL': 'SNOONU',
    }
    filtered = {k: v for k, v in row.items() if k in cols}
    extra = ', CREATEDDATE' if 'CREATEDDATE' in cols else ''
    extra_val = ', SYSDATE' if 'CREATEDDATE' in cols else ''
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO CUSTOMER ({', '.join(filtered)}{extra}) VALUES ({', '.join(':' + k for k in filtered)}{extra_val})",
                filtered,
            )
        conn.commit()
    return {'customercode': code, 'customername': 'SNOONU'}


def _ensure_snoonu_bill_customer(location_code: int) -> Tuple[Optional[Dict[str, Any]], bool, str]:
    found = _find_customer_named_snoonu(location_code)
    created = False
    if not found:
        found = _create_snoonu_bill_customer(location_code)
        created = bool(found)
    if not found:
        return None, False, 'Could not find or create customer SNOONU.'
    _ensure_snoonu_credit_billing(location_code, found.get('customercode'))
    payload = _customer_payload(
        location_code,
        found.get('customercode'),
        created,
        fallback_name=str(found.get('customername') or 'SNOONU'),
    )
    if not payload.get('name'):
        payload['name'] = 'SNOONU'
    payload['billing_type'] = 'CREDIT'
    payload['customer_billing_type'] = 'CREDIT'
    note = 'Customer SNOONU created.' if created else 'Customer SNOONU selected.'
    return payload, created, note


def _loyalty_payload(location_code: int, code: Any, created: bool, fallback_name: str = '', phone: str = '') -> Dict[str, Any]:
    rows = get_customer_loyalty_for_picker(int(location_code), picker_search=str(code or ''), picker_limit=20)
    hit = None
    for row in rows or []:
        if str(row.get('code') or '').strip() == str(code).strip():
            hit = row
            break
    if not hit and rows:
        hit = rows[0]
    hit = hit or {}
    return {
        'code': str(hit.get('code') or code or ''),
        'name': str(hit.get('name') or fallback_name or ''),
        'phone': str(hit.get('phone') or phone or ''),
        'totalpoints': hit.get('totalpoints') or 0,
        'created': created,
        'location_code': int(location_code),
    }


def _find_loyalty_by_mobile(location_code: int, e164: str) -> Optional[Dict[str, Any]]:
    if not _table_exists('CUSTOMERLOYALTY'):
        return None
    digits = re.sub(r'\D+', '', e164 or '')
    last8 = digits[-8:] if len(digits) >= 8 else digits
    if not last8:
        return None
    cols = {str(c).upper() for c in (_get_table_columns('CUSTOMERLOYALTY') or [])}
    points_sel = 'NVL(c.TOTALPOINTS, 0) AS totalpoints' if 'TOTALPOINTS' in cols else '0 AS totalpoints'
    phone_sel = "TRIM(NVL(c.MOB, NVL(c.PHONE1, c.PHONE2))) AS phone" if 'MOB' in cols else "TRIM(NVL(c.PHONE1, c.PHONE2)) AS phone"
    where_bits = []
    if 'MOB' in cols:
        where_bits.append("REGEXP_REPLACE(NVL(c.MOB, ''), '[^0-9]', '') LIKE :q")
    if 'PHONE1' in cols:
        where_bits.append("REGEXP_REPLACE(NVL(c.PHONE1, ''), '[^0-9]', '') LIKE :q")
    if 'PHONE2' in cols:
        where_bits.append("REGEXP_REPLACE(NVL(c.PHONE2, ''), '[^0-9]', '') LIKE :q")
    if not where_bits:
        return None
    rows = _safe_rows(
        f"""
        SELECT c.CUSTOMERCODE AS code, c.CUSTOMERNAME AS name, {phone_sel}, {points_sel}
        FROM CUSTOMERLOYALTY c
        WHERE c.LOCATIONCODE = :loc AND ({' OR '.join(where_bits)})
        FETCH FIRST 1 ROWS ONLY
        """,
        {'loc': int(location_code), 'q': f'%{last8}%'},
    )
    return rows[0] if rows else None


def _ensure_loyalty_customer(extracted: Dict[str, Any], location_code: int) -> Tuple[Optional[Dict[str, Any]], str]:
    mobile_raw = str(extracted.get('mobile') or extracted.get('phone') or '').strip()
    address = str(extracted.get('address') or '').strip()
    if not mobile_raw:
        return None, 'No mobile on the Snoonu invoice — loyalty customer not created.'
    ok, msg, e164 = validate_mobile(mobile_raw, required=True)
    if not ok:
        return None, msg or 'Snoonu mobile is not a valid Qatar number — loyalty customer not created.'
    display_name = (_english_customer_name(extracted) or f'SNOONU {e164[-8:]}')[:40]
    existing = _find_loyalty_by_mobile(location_code, e164)
    if existing:
        old_name = str(existing.get('name') or '')
        if display_name and _has_arabic(old_name):
            _update_loyalty_name(location_code, existing.get('code'), display_name)
        payload = _loyalty_payload(
            location_code,
            existing.get('code'),
            False,
            fallback_name=display_name if _has_arabic(old_name) else (old_name or display_name),
            phone=str(existing.get('phone') or e164),
        )
        return payload, 'Loyalty customer matched by mobile.'
    payload_in = {
        'customername': display_name,
        'name': display_name,
        'mob': e164[:15],
        'mobile': e164[:15],
        'phone1': e164[:15],
        'address1': address[:40],
    }
    ok_ins, err = insert_customer_loyalty_row(int(location_code), payload_in)
    if not ok_ins:
        again = _find_loyalty_by_mobile(location_code, e164)
        if again:
            payload = _loyalty_payload(
                location_code,
                again.get('code'),
                False,
                fallback_name=str(again.get('name') or display_name),
                phone=str(again.get('phone') or e164),
            )
            return payload, 'Loyalty customer matched by mobile.'
        return None, err or 'Could not create loyalty customer.'
    code = payload_in.get('customercode')
    payload = _loyalty_payload(location_code, code, True, fallback_name=display_name, phone=e164)
    return payload, 'Loyalty customer created from Snoonu mobile.'


def _snoonu_default_warehouse() -> Optional[Dict[str, Any]]:
    from db import get_warehouse_master_by_code

    row = get_warehouse_master_by_code('WH001')
    if not row:
        return None
    wid = row.get('warehouse_id') or row.get('WAREHOUSE_ID')
    code = str(row.get('warehouse_code') or row.get('WAREHOUSE_CODE') or 'WH001').strip() or 'WH001'
    name = str(row.get('warehouse_name') or row.get('WAREHOUSE_NAME') or code).strip()
    if wid in (None, ''):
        return None
    return {
        'id': str(wid),
        'warehouse_id': str(wid),
        'code': code,
        'warehouse_code': code,
        'name': name,
        'warehouse_name': name,
    }


def ensure_snoonu_bill_customer() -> Dict[str, Any]:
    location_code = _location_code()
    customer, created, note = _ensure_snoonu_bill_customer(location_code)
    if not customer:
        raise ValueError(note or 'Could not find or create customer SNOONU.')
    return {
        'success': True,
        'customer': customer,
        'customer_note': note,
        'created': created,
        'warehouse': _snoonu_default_warehouse(),
    }


_BARCODE_TOKEN_RE = re.compile(r'\d{8,18}(?:-\d+)?')


def _add_barcode_query(ordered: List[str], seen: set, value: Any) -> None:
    raw = str(value or '').strip()
    if not raw:
        return
    tokens = [raw]
    tokens.extend(_BARCODE_TOKEN_RE.findall(raw))
    compact = re.sub(r'[\s]', '', raw)
    if compact and compact != raw:
        tokens.append(compact)
    digits = re.sub(r'\D', '', raw)
    if len(digits) >= 8:
        tokens.append(digits)
    for token in tokens:
        token = str(token or '').strip()
        if not token:
            continue
        looks_barcode = bool(_BARCODE_TOKEN_RE.fullmatch(token) or (token.isdigit() and 8 <= len(token) <= 18))
        if not looks_barcode:
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)


def _barcode_queries_from_line(raw: Dict[str, Any]) -> List[str]:
    seen: set = set()
    ordered: List[str] = []
    for key in ('barcode', 'sku', 'ean', 'upc', 'gtin', 'manufacturer_id', 'manufacturerid'):
        _add_barcode_query(ordered, seen, raw.get(key))
    for key in ('item_name', 'itemname', 'name', 'product_name', 'description', 'product'):
        text = str(raw.get(key) or '')
        for token in _BARCODE_TOKEN_RE.findall(text):
            _add_barcode_query(ordered, seen, token)
    return ordered


_GIFT_WRAP_NAME_RE = re.compile(
    r'gift\s*wrap|gift\s*wrapping|wrapping\b|تغليف(?:\s*هدية)?',
    re.I,
)
_GIFT_WRAP_SKU_NAMES = {
    'FREE GIFT WRAP',
    'CLASSIC GIFT WRAP FOR BOYS',
    'CLASSIC GIFT WRAP FOR GIRLS',
    'PREMIUM GIFT WRAP FOR BOYS',
    'PREMIUM GIFT WRAP FOR GIRLS',
    'NEWBORN GIFT WRAP',
    'BIRTHDAY GIFT WRAP',
}


def _line_description(raw: Dict[str, Any]) -> str:
    for key in ('item_name', 'itemname', 'name', 'product_name', 'description', 'product'):
        text = str(raw.get(key) or '').strip()
        if text:
            return text
    return ''


def _is_gift_wrap_text(text: str) -> bool:
    return bool(_GIFT_WRAP_NAME_RE.search(str(text or '')))


def _name_tokens(text: str) -> set:
    raw = re.sub(r'[^a-z0-9\u0600-\u06ff]+', ' ', str(text or '').lower())
    tokens = {t for t in raw.split() if t}
    extra: set = set()
    for token in list(tokens):
        if token.startswith('wrapp'):
            extra.add('wrap')
        if token in ('تغليف', 'تغليفه', 'تغليفها'):
            extra.update({'wrap', 'gift'})
        if token in ('boy', 'boys', 'ولد', 'اولاد', 'للأولاد', 'للاولاد'):
            extra.update({'boy', 'boys'})
        if token in ('girl', 'girls', 'بنت', 'بنات', 'للبنات'):
            extra.update({'girl', 'girls'})
    return tokens | extra


def _gift_wrap_catalog(location_code: int) -> List[Dict[str, Any]]:
    rows = _safe_rows(
        """
        SELECT ITEMCODE AS itemcode,
               ITEMNAME AS itemname,
               ITEMNAMEARA AS itemnameara,
               MANUFACTURERID AS manufacturerid,
               RETAILPRICE AS retailprice
        FROM ITEMMASTER
        WHERE LOCATIONCODE = :loc
          AND (
            UPPER(NVL(MANUFACTURERID, ' ')) LIKE 'GW%'
            OR UPPER(TRIM(ITEMNAME)) IN (
              'FREE GIFT WRAP',
              'CLASSIC GIFT WRAP FOR BOYS',
              'CLASSIC GIFT WRAP FOR GIRLS',
              'PREMIUM GIFT WRAP FOR BOYS',
              'PREMIUM GIFT WRAP FOR GIRLS',
              'NEWBORN GIFT WRAP',
              'BIRTHDAY GIFT WRAP'
            )
          )
        ORDER BY ITEMCODE
        """,
        {'loc': int(location_code)},
    )
    return [dict(row) for row in (rows or [])]


def _score_gift_wrap_hit(query: str, row: Dict[str, Any], amount: float) -> int:
    name = str(row.get('itemname') or '')
    arabic = str(row.get('itemnameara') or '')
    qtok = _name_tokens(query)
    ntok = _name_tokens(f'{name} {arabic}')
    if not qtok or not ntok:
        return 0
    overlap = qtok & ntok
    score = 10 * len(overlap)
    if qtok == _name_tokens(name) or qtok == _name_tokens(arabic):
        score += 80
    if overlap & {'gift', 'wrap', 'wrapping', 'تغليف'}:
        score += 20
    try:
        retail = float(row.get('retailprice') or 0)
    except (TypeError, ValueError):
        retail = 0.0
    if abs(retail - float(amount or 0)) < 0.051:
        score += 30
    elif abs(retail - float(amount or 0)) <= 1:
        score += 8
    for left, right in (
        ({'boy', 'boys'}, {'boy', 'boys'}),
        ({'girl', 'girls'}, {'girl', 'girls'}),
        ({'classic', 'كلاسيكي'}, {'classic', 'كلاسيكي'}),
        ({'premium', 'فاخر'}, {'premium', 'فاخر'}),
        ({'newborn', 'حديثي'}, {'newborn', 'حديثي'}),
        ({'birthday', 'ميلاد'}, {'birthday', 'ميلاد'}),
        ({'free', 'مجاني'}, {'free', 'مجاني'}),
    ):
        if qtok & left and ntok & right:
            score += 18
    return score


def _match_gift_wrap_by_description(
    raw: Dict[str, Any],
    location_code: int,
    amount: float,
) -> Optional[Dict[str, Any]]:
    """Gift wrap lines have a description + amount, no barcode / qty."""
    name = _line_description(raw)
    if not name or not _is_gift_wrap_text(name):
        return None
    best = None
    best_score = 0
    for row in _gift_wrap_catalog(location_code):
        score = _score_gift_wrap_hit(name, row, amount)
        if score > best_score:
            best = row
            best_score = score
    if not best or best_score < 20:
        return None
    from addons.pos_billing.controllers.routes import _pos_lookup_item_row
    from db import get_item_by_code

    mid = str(best.get('manufacturerid') or '').strip()
    hit = _pos_lookup_item_row(location_code, mid) if mid else None
    if not hit:
        try:
            hit = get_item_by_code(int(best.get('itemcode')), location_code)
        except (TypeError, ValueError):
            hit = None
    return hit


def _wrap_payload_from_raw(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    nested = raw.get('gift_wrap') or raw.get('wrapping') or raw.get('gift_wrapping')
    if isinstance(nested, dict):
        name = _line_description(nested) or str(
            nested.get('type') or nested.get('style') or nested.get('gift_wrap_name') or ''
        ).strip()
        amount = _to_float(nested.get('amount') or nested.get('fee') or nested.get('price'))
        if name or amount > 0:
            return {'item_name': name, 'amount': amount}
    name = str(
        raw.get('gift_wrap_name') or raw.get('wrap_name') or raw.get('gift_wrapping_name') or ''
    ).strip()
    amount = _to_float(raw.get('gift_wrap_amount') or raw.get('wrap_amount') or raw.get('wrapping_amount'))
    if name or amount > 0:
        return {'item_name': name, 'amount': amount}
    return None


def _is_standalone_wrap_line(raw: Dict[str, Any]) -> bool:
    if _barcode_queries_from_line(raw):
        return False
    name = _line_description(raw)
    if not _is_gift_wrap_text(name):
        return False
    return len(name) <= 80 or name.strip().upper() in _GIFT_WRAP_SKU_NAMES


def _normalize_extracted_lines(lines: Any) -> List[Dict[str, Any]]:
    """Attach wrap-only lines to the product printed above them."""
    out: List[Dict[str, Any]] = []
    for raw in lines or []:
        if not isinstance(raw, dict):
            continue
        wrap = _wrap_payload_from_raw(raw)
        if _is_standalone_wrap_line(raw):
            attached = wrap or {
                'item_name': _line_description(raw),
                'amount': _to_float(raw.get('amount') or raw.get('line_total') or raw.get('total')),
            }
            if out and not _wrap_payload_from_raw(out[-1]):
                out[-1] = dict(out[-1])
                out[-1]['gift_wrap_name'] = attached.get('item_name') or ''
                out[-1]['gift_wrap_amount'] = attached.get('amount') or 0
            continue
        row = dict(raw)
        if wrap:
            row['gift_wrap_name'] = wrap.get('item_name') or row.get('gift_wrap_name') or ''
            row['gift_wrap_amount'] = wrap.get('amount') or row.get('gift_wrap_amount') or 0
        out.append(row)
    return out


def _wrap_unit_fee(wrap_amount: float, item_qty: float) -> float:
    fee = float(wrap_amount or 0)
    qty = max(float(item_qty or 0), 1.0)
    if fee <= 0:
        return 0.0
    if qty > 1:
        unit = round(fee / qty, 4)
        if abs(unit - 8) < 0.05 or abs(unit - 16) < 0.05:
            return unit
    return fee


def _finish_matched_row(
    *,
    matched: Optional[Dict[str, Any]],
    qty: float,
    unit_price: float,
    amount: float,
    query_used: str,
    queries: List[str],
    raw: Dict[str, Any],
) -> Dict[str, Any]:
    if matched:
        matched = dict(matched)
        if query_used and (
            _BARCODE_TOKEN_RE.fullmatch(query_used)
            or (query_used.isdigit() and 8 <= len(query_used) <= 18)
        ):
            matched['manufacturerid'] = query_used
            matched['manufacturer_id'] = query_used
        if unit_price > 0:
            matched['retailprice'] = unit_price
            matched['barcode_retail_price'] = unit_price
    return {
        'matched': bool(matched),
        'qty': qty,
        'unit_price': unit_price,
        'amount': amount,
        'price_is_line_total': True,
        'query_used': query_used,
        'queries_tried': queries,
        'ai': raw,
        'item': matched,
    }


def _build_wrap_result(
    wrap: Dict[str, Any],
    item_qty: float,
    location_code: int,
) -> Dict[str, Any]:
    qty = max(float(item_qty or 0), 1.0)
    unit_fee = _wrap_unit_fee(_to_float(wrap.get('amount')), qty)
    amount = round(unit_fee * qty, 4) if unit_fee > 0 else _to_float(wrap.get('amount'))
    raw = {'item_name': wrap.get('item_name') or 'Gift Wrapping', 'amount': unit_fee or amount, 'qty': qty}
    matched = _match_gift_wrap_by_description(raw, location_code, unit_fee or amount)
    return _finish_matched_row(
        matched=matched,
        qty=qty,
        unit_price=unit_fee if unit_fee > 0 else amount,
        amount=amount,
        query_used=str(wrap.get('item_name') or ''),
        queries=[],
        raw=raw,
    )


def _match_lines(extracted: Dict[str, Any], location_code: int) -> List[Dict[str, Any]]:
    from addons.pos_billing.controllers.routes import _pos_lookup_item_row
    from db import get_item_by_alternate_barcode, get_item_by_manufacturer_id

    results: List[Dict[str, Any]] = []
    for raw in _normalize_extracted_lines(extracted.get('lines') or []):
        line_name = _line_description(raw)
        qty = _to_float(raw.get('qty'), 1.0)
        if qty <= 0:
            qty = 1.0
        amount = _to_float(raw.get('amount') or raw.get('line_total') or raw.get('total'))
        unit_price = _to_float(raw.get('unit_price') or raw.get('price') or raw.get('rate'))
        if amount <= 0 and unit_price > 0:
            amount = unit_price
        wrap = _wrap_payload_from_raw(raw)
        if wrap:
            deduct = round(_wrap_unit_fee(_to_float(wrap.get('amount')), qty) * qty, 4)
            if deduct > 0 and amount > deduct:
                amount = round(amount - deduct, 4)
        if amount > 0:
            unit_price = round(amount / qty, 4)
        elif unit_price > 0:
            amount = round(unit_price * qty, 4)
        queries = _barcode_queries_from_line(raw)
        matched = None
        query_used = ''
        for query in queries:
            hit = _pos_lookup_item_row(location_code, query)
            if not hit:
                hit = get_item_by_manufacturer_id(query, location_code)
            if not hit:
                hit = get_item_by_alternate_barcode(query, location_code)
            if hit:
                matched = hit
                query_used = query
                break
        row = _finish_matched_row(
            matched=matched,
            qty=qty,
            unit_price=unit_price,
            amount=amount,
            query_used=query_used,
            queries=queries,
            raw=raw,
        )
        if wrap:
            row['wrap_fee_each'] = _wrap_unit_fee(_to_float(wrap.get('amount')), qty)
            row['wrap_deducted'] = round((row.get('wrap_fee_each') or 0) * qty, 4)
        results.append(row)
        if wrap:
            results.append(_build_wrap_result(wrap, qty, location_code))
    return results


def _extract_with_openai(*, text: str = '', image_bytes: Optional[bytes] = None, mime: str = 'image/png') -> Dict[str, Any]:
    api_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise ValueError('OPENAI_API_KEY is not configured.')
    from openai import OpenAI

    model = (os.environ.get('OPENAI_VISION_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini').strip()
    client = OpenAI(api_key=api_key, timeout=90.0)
    if image_bytes:
        data_uri = f'data:{mime};base64,{base64.b64encode(image_bytes).decode("ascii")}'
        prompt = 'Extract the Snoonu invoice / order as specified.'
        if text:
            prompt += '\n\nAlso use this pasted text:\n' + text
        messages = [
            {'role': 'system', 'content': _SNOONU_SYS},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ],
            },
        ]
    else:
        messages = [
            {'role': 'system', 'content': _SNOONU_SYS},
            {'role': 'user', 'content': 'Extract the Snoonu invoice below.\n\n---\n\n' + text},
        ]
    completion = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=messages,
        max_tokens=2500,
    )
    return _parse_json_object((completion.choices[0].message.content or '').strip())


def import_snoonu_invoice(
    *,
    text: str = '',
    image_bytes: Optional[bytes] = None,
    mime: str = 'image/png',
    filename: str = '',
) -> Dict[str, Any]:
    from addons.pos_billing.controllers.routes import (
        _pos_bytes_looks_like_pdf,
        _pos_pdf_first_page_to_png_bytes,
        _pos_upload_looks_like_pdf,
    )

    text = (text or '').strip()
    raw = image_bytes
    use_mime = mime or 'image/png'
    if raw:
        if _pos_upload_looks_like_pdf(use_mime, filename) or _pos_bytes_looks_like_pdf(raw):
            png = _pos_pdf_first_page_to_png_bytes(raw, max_bytes_out=6 * 1024 * 1024)
            if not png:
                raise ValueError('Could not read that PDF. Try a screenshot of the Snoonu invoice.')
            raw = png
            use_mime = 'image/png'
        if not str(use_mime).startswith('image/'):
            use_mime = 'image/jpeg'
    if not raw and not text:
        raise ValueError('Paste a Snoonu invoice or upload a screenshot / PDF.')

    extracted = _extract_with_openai(text=text, image_bytes=raw, mime=use_mime)
    location_code = _location_code()
    order_no = str(extracted.get('order_no') or extracted.get('invoice_no') or '').strip()
    if order_no:
        inv_table = _detect_table(['BILLHDR', 'billhdr'])
        existing = (
            _sales_orderno_find_billno(inv_table, location_code, order_no.upper())
            if inv_table
            else None
        )
        if existing is not None:
            return {
                'success': False,
                'already_saved': True,
                'order_no': order_no,
                'billno': existing,
                'error': 'already saved',
            }
    customer, _created, customer_note = _ensure_snoonu_bill_customer(location_code)
    loyalty, loyalty_note = _ensure_loyalty_customer(extracted, location_code)
    results = _match_lines(extracted, location_code)
    matched = sum(1 for row in results if row.get('matched'))
    notes = [n for n in (customer_note, loyalty_note) if n]
    bill_date, delivery_date = _invoice_dates(extracted)
    return {
        'success': True,
        'extracted': extracted,
        'customer': customer,
        'customer_note': ' '.join(notes),
        'loyalty_customer': loyalty,
        'loyalty_note': loyalty_note,
        'order_no': str(extracted.get('order_no') or extracted.get('invoice_no') or '').strip(),
        'bill_date': bill_date,
        'delivery_date': delivery_date,
        'warehouse': _snoonu_default_warehouse(),
        'delivery_fee': _to_float(extracted.get('delivery_fee')),
        'total': _to_float(extracted.get('total')),
        'results': results,
        'matched': matched,
        'unmatched': max(0, len(results) - matched),
    }
