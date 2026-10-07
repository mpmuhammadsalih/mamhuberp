"""Sales invoice PDF template catalog and theme presets."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Stable keys used in URLs (?template=) and localStorage.
DEFAULT_INVOICE_TEMPLATE = 'classic'

INVOICE_TEMPLATES: List[Dict[str, str]] = [
    {
        'id': 'classic',
        'name': 'Classic Blue',
        'tagline': 'Navy header, traditional invoice layout',
        'swatch': '#1a3a6b',
    },
    {
        'id': 'modern',
        'name': 'Modern Teal',
        'tagline': 'Clean centered brand, soft teal accents',
        'swatch': '#0f766e',
    },
    {
        'id': 'compact',
        'name': 'Compact Gray',
        'tagline': 'Dense lines for long invoices',
        'swatch': '#475569',
    },
    {
        'id': 'slate',
        'name': 'Slate Banner',
        'tagline': 'Full-width dark banner with bold totals',
        'swatch': '#0f172a',
    },
    {
        'id': 'gulfnova',
        'name': 'Gulf Nova Retail',
        'tagline': 'Navy + red retail look with thank-you footer',
        'swatch': '#c41e3a',
    },
]

_VALID_IDS = {t['id'] for t in INVOICE_TEMPLATES}


def normalize_invoice_template(raw: Any) -> str:
    key = str(raw or '').strip().lower().replace(' ', '_').replace('-', '_')
    aliases = {
        'default': 'classic',
        'blue': 'classic',
        'navy': 'classic',
        'teal': 'modern',
        'clean': 'modern',
        'dense': 'compact',
        'minimal': 'compact',
        'dark': 'slate',
        'banner': 'slate',
        'bold': 'slate',
        'retail': 'gulfnova',
        'gnt': 'gulfnova',
        'gulf': 'gulfnova',
        'gulf_nova': 'gulfnova',
        'red': 'gulfnova',
    }
    key = aliases.get(key, key)
    return key if key in _VALID_IDS else DEFAULT_INVOICE_TEMPLATE


def list_invoice_templates() -> List[Dict[str, str]]:
    return [dict(t) for t in INVOICE_TEMPLATES]


_SETTING_KEY = 'sales_invoice_pdf_template'
_SETTINGS_TABLE = 'NEXA_APP_SETTINGS'


def _ensure_app_settings_table() -> bool:
    """Create tenant key/value settings table if missing."""
    try:
        from db import _TABLE_EXISTS_CACHE, _get_connection, _table_exists
    except Exception as exc:
        print(f'[WARN nexa_app_settings import] {exc}')
        return False
    if _table_exists(_SETTINGS_TABLE):
        return True
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE {_SETTINGS_TABLE} (
                        SETTING_KEY   VARCHAR2(80 BYTE) PRIMARY KEY,
                        SETTING_VALUE VARCHAR2(200 BYTE),
                        UPDATED_AT    DATE
                    )
                    """
                )
            conn.commit()
        try:
            _TABLE_EXISTS_CACHE.pop(_SETTINGS_TABLE, None)
            _TABLE_EXISTS_CACHE.pop(_SETTINGS_TABLE.lower(), None)
        except Exception:
            pass
        return True
    except Exception as exc:
        # Another session may have created it concurrently.
        try:
            if _table_exists(_SETTINGS_TABLE):
                return True
        except Exception:
            pass
        print(f'[WARN nexa_app_settings create] {exc}')
        return False


def get_saved_invoice_template() -> str:
    """Tenant-wide default invoice PDF template (used by web + mobile)."""
    return get_saved_invoice_template_info()['template']


def get_saved_invoice_template_info() -> Dict[str, Any]:
    """Return ``{template, saved}`` — ``saved`` is False when using the built-in default."""
    try:
        from db import _safe_rows
    except Exception:
        return {'template': DEFAULT_INVOICE_TEMPLATE, 'saved': False}
    if not _ensure_app_settings_table():
        return {'template': DEFAULT_INVOICE_TEMPLATE, 'saved': False}
    try:
        rows = _safe_rows(
            f"SELECT SETTING_VALUE FROM {_SETTINGS_TABLE} WHERE SETTING_KEY = :k",
            {'k': _SETTING_KEY},
        ) or []
        if rows:
            return {
                'template': normalize_invoice_template(rows[0].get('setting_value')),
                'saved': True,
            }
    except Exception:
        pass
    return {'template': DEFAULT_INVOICE_TEMPLATE, 'saved': False}


def set_saved_invoice_template(raw: Any) -> str:
    """Persist tenant-wide invoice PDF template. Returns normalized key.

    Raises ``RuntimeError`` when the setting cannot be written.
    """
    key = normalize_invoice_template(raw)
    try:
        from db import _get_connection
    except Exception as exc:
        raise RuntimeError(f'Database unavailable: {exc}') from exc
    if not _ensure_app_settings_table():
        raise RuntimeError('Could not create or open NEXA_APP_SETTINGS.')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(1) FROM {_SETTINGS_TABLE} WHERE SETTING_KEY = :k",
                    {'k': _SETTING_KEY},
                )
                exists = int((cur.fetchone() or [0])[0] or 0) > 0
                if exists:
                    cur.execute(
                        f"""
                        UPDATE {_SETTINGS_TABLE}
                           SET SETTING_VALUE = :v, UPDATED_AT = SYSDATE
                         WHERE SETTING_KEY = :k
                        """,
                        {'v': key, 'k': _SETTING_KEY},
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {_SETTINGS_TABLE} (SETTING_KEY, SETTING_VALUE, UPDATED_AT)
                        VALUES (:k, :v, SYSDATE)
                        """,
                        {'k': _SETTING_KEY, 'v': key},
                    )
            conn.commit()
    except Exception as exc:
        raise RuntimeError(f'Failed to save invoice template: {exc}') from exc
    return key


def resolve_invoice_template(raw: Any = None) -> str:
    """URL/arg override if present; otherwise tenant saved default."""
    explicit = str(raw or '').strip()
    if explicit:
        return normalize_invoice_template(explicit)
    return get_saved_invoice_template()


def invoice_template_theme(template_key: Any) -> Dict[str, Any]:
    """Colors / spacing / layout mode for ReportLab cashbilldup PDF."""
    key = normalize_invoice_template(template_key)
    # Shared defaults (classic)
    base: Dict[str, Any] = {
        'id': key,
        'primary': '#1a3a6b',
        'border': '#c5cdd8',
        'row_alt': '#f5f7fa',
        'text': '#1a1a1a',
        'muted': '#555f6b',
        'gt_bg': '#eef3fb',
        'title_size': 18,
        'co_name_size': 13,
        'pad': 4,
        'top_margin': 0.4,
        'bottom_margin': 2.55,
        'left_margin': 0.45,
        'right_margin': 0.45,
        'layout': 'split',  # split | centered | banner | dense
        'logo_size': 0.7,
        'table_header_white': True,
        'accent_rule': True,
    }
    if key == 'modern':
        base.update({
            'primary': '#0f766e',
            'border': '#99f6e4',
            'row_alt': '#f0fdfa',
            'gt_bg': '#ccfbf1',
            'muted': '#115e59',
            'layout': 'centered',
            'title_size': 16,
            'co_name_size': 14,
            'logo_size': 0.85,
            'top_margin': 0.35,
        })
    elif key == 'compact':
        base.update({
            'primary': '#334155',
            'border': '#cbd5e1',
            'row_alt': '#f8fafc',
            'gt_bg': '#e2e8f0',
            'muted': '#64748b',
            'layout': 'dense',
            'title_size': 14,
            'co_name_size': 11,
            'pad': 2,
            'top_margin': 0.28,
            'bottom_margin': 2.35,
            'left_margin': 0.35,
            'right_margin': 0.35,
            'logo_size': 0.5,
        })
    elif key == 'slate':
        base.update({
            'primary': '#0f172a',
            'border': '#94a3b8',
            'row_alt': '#f1f5f9',
            'gt_bg': '#1e293b',
            'gt_fg': '#f8fafc',
            'muted': '#64748b',
            'layout': 'banner',
            'title_size': 20,
            'co_name_size': 12,
            'logo_size': 0.65,
            'table_header_white': True,
            'accent_rule': False,
        })
    elif key == 'gulfnova':
        base.update({
            'primary': '#002147',
            'accent': '#C00000',
            'border': '#c8cdd4',
            'row_alt': '#ffffff',
            'gt_bg': '#C00000',
            'gt_fg': '#ffffff',
            'muted': '#555f6b',
            'layout': 'retail',
            'title_size': 22,
            'co_name_size': 14,
            'logo_size': 0.9,
            'pad': 5,
            'top_margin': 0.35,
            'bottom_margin': 2.55,
            'table_header_white': True,
            'accent_rule': False,
            'discount_accent': True,
            'thank_you_footer': False,
            'skip_signature_boxes': False,
        })
    return base


def sample_invoice_print_payload() -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Demo header/lines for template preview PDFs."""
    header = {
        'customercode': 'C-1001',
        'customername': 'Sample Trading Co.',
        'address': '12 Business Bay, Dubai, UAE',
        'telephone': '+971 4 000 0000',
        'mobile': '+971 50 000 0000',
        'billdate': '2026-08-15',
        'billtime': '10:30 AM',
        'remarks': 'Template preview — sample data only',
        'orderno': 'SO-10045',
        'createdby': 'demo',
        'discountamount': 5.0,
        'netbillamount': 295.0,
        'locationcode': 1,
    }
    lines = [
        {
            'slno': 1,
            'itemcode': '10001',
            'itemname': 'Premium Coffee Beans 1kg',
            'quantity': 2,
            'unitofmeasurement': 'NOS',
            'rate': 75.0,
            'itdisc': 0,
            'amount': 150.0,
        },
        {
            'slno': 2,
            'itemcode': '10022',
            'itemname': 'Ceramic Mug Set',
            'quantity': 3,
            'unitofmeasurement': 'NOS',
            'rate': 50.0,
            'itdisc': 5.0,
            'amount': 145.0,
        },
    ]
    return header, lines
