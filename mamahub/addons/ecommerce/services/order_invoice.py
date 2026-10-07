"""Post an ecommerce MH_ORDER as an ERP sales invoice (BILLHDR / BILLDTL)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _get_connection,
    _safe_rows,
    get_customers_master_list,
    get_item_by_code,
    save_sales_invoice,
)

from addons.ecommerce import orders_db
from addons.ecommerce import settings_store
from addons.ecommerce.services.common import resolve_location_code

_ONLINE_CUSTOMER_CODE = 90001
_ONLINE_CUSTOMER_NAME = 'Online Sales'


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _format_address(raw: Any) -> str:
    text = str(raw or '').strip()
    if not text:
        return ''
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text[:240]
    if not isinstance(data, dict):
        return text[:240]
    parts = [
        str(data.get('street') or '').strip(),
        str(data.get('area') or '').strip(),
        str(data.get('landmark') or '').strip(),
        str(data.get('city') or '').strip(),
        str(data.get('zone') or '').strip(),
        str(data.get('country') or '').strip(),
    ]
    return ', '.join(part for part in parts if part)[:240]


def _web_customer_name(order: Dict[str, Any]) -> str:
    name = ' '.join(
        part
        for part in (
            str(order.get('customer_first_name') or '').strip(),
            str(order.get('customer_last_name') or '').strip(),
        )
        if part
    ).strip()
    if name:
        return name[:120]
    email = str(order.get('customer_email') or '').strip()
    return (email or 'Online customer')[:120]


def _ensure_online_sales_customer(location_code: int) -> Tuple[Optional[int], str]:
    """Create a cash 'Online Sales' customer when the ERP has none configured."""
    loc = int(location_code)
    existing = _safe_rows(
        """
        SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername
        FROM CUSTOMER
        WHERE LOCATIONCODE = :loc AND CUSTOMERCODE = :code
        FETCH FIRST 1 ROWS ONLY
        """,
        {'loc': loc, 'code': _ONLINE_CUSTOMER_CODE},
    )
    if existing:
        return _ONLINE_CUSTOMER_CODE, str(existing[0].get('customername') or _ONLINE_CUSTOMER_NAME)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO CUSTOMER (
                        LOCATIONCODE, CUSTOMERCODE, CUSTOMERNAME,
                        CREDITLIMIT, CREDITTERMS, SALESMANCODE, FLAG, CUSTOMERCATEGORY,
                        BYSALESMAN, ROUTENO, CREATEDSTATUS, TRANSFERBRANCH, PRINTSEPRATE,
                        QID, ACTIVE, COUNTERSALE, DUEDAYS, MAINGROUP, CUSTOMER_BILLING_TYPE
                    ) VALUES (
                        :loc, :code, :name,
                        0, 0, 0, 'C', 0,
                        0, 0, 'N', 'N', 'N',
                        0, 'Y', 'Y', 0, 0, 'CASH'
                    )
                    """,
                    {'loc': loc, 'code': _ONLINE_CUSTOMER_CODE, 'name': _ONLINE_CUSTOMER_NAME},
                )
            conn.commit()
    except Exception:
        retry = _safe_rows(
            """
            SELECT CUSTOMERCODE AS customercode, CUSTOMERNAME AS customername
            FROM CUSTOMER
            WHERE LOCATIONCODE = :loc AND CUSTOMERCODE = :code
            FETCH FIRST 1 ROWS ONLY
            """,
            {'loc': loc, 'code': _ONLINE_CUSTOMER_CODE},
        )
        if retry:
            return _ONLINE_CUSTOMER_CODE, str(retry[0].get('customername') or _ONLINE_CUSTOMER_NAME)
        return None, ''
    try:
        settings_store.save_store_settings({'erp_customer_code': str(_ONLINE_CUSTOMER_CODE)})
    except Exception:
        pass
    return _ONLINE_CUSTOMER_CODE, _ONLINE_CUSTOMER_NAME


def resolve_erp_customer() -> Tuple[Optional[int], str, str]:
    """Return (customer_code, customer_name, billing_type) for web invoices."""
    settings = settings_store.load_store_settings()
    configured = _as_int(settings.get('erp_customer_code'))
    rows = get_customers_master_list(for_picker=True, picker_limit=80, picker_billing_type='CASH')
    if not rows:
        rows = get_customers_master_list(for_picker=True, picker_limit=80)
    picked = None
    if configured:
        for row in rows or []:
            code = _as_int(row.get('CODE') or row.get('code') or row.get('customercode'))
            if code == configured:
                picked = row
                break
        if picked is None:
            all_rows = get_customers_master_list(for_picker=True, picker_search=str(configured), picker_limit=20)
            for row in all_rows or []:
                code = _as_int(row.get('CODE') or row.get('code') or row.get('customercode'))
                if code == configured:
                    picked = row
                    break
    if picked is None and rows:
        picked = rows[0]
    if not picked:
        created_code, created_name = _ensure_online_sales_customer(resolve_location_code())
        if created_code:
            return created_code, created_name, 'CASH'
        return None, '', ''
    code = _as_int(picked.get('CODE') or picked.get('code') or picked.get('customercode'))
    name = str(picked.get('NAME') or picked.get('name') or picked.get('customername') or '').strip()
    billing = str(
        picked.get('customer_billing_type')
        or picked.get('CUSTOMER_BILLING_TYPE')
        or 'CASH'
    ).strip().upper() or 'CASH'
    if not code:
        created_code, created_name = _ensure_online_sales_customer(resolve_location_code())
        if created_code:
            return created_code, created_name, 'CASH'
        return None, '', ''
    return code, name or f'Customer {code}', billing


def _invoice_lines(order: Dict[str, Any], location_code: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    lines: List[Dict[str, Any]] = []
    settings = settings_store.load_store_settings()
    for row in order.get('line_items') or []:
        item_code = _as_int(row.get('item_code'))
        qty = _as_float(row.get('quantity'))
        if not item_code or qty <= 0:
            continue
        item = get_item_by_code(item_code, location_code) or {}
        uom = str(
            item.get('baseuom')
            or item.get('BASEUOM')
            or item.get('uom')
            or 'PCS'
        ).strip() or 'PCS'
        rate = _as_float(row.get('unit_price'))
        discount = max(_as_float(row.get('discount_amount')), 0.0)
        amount = _as_float(row.get('line_total'))
        if amount <= 0:
            amount = max(rate * qty - discount, 0.0)
        lines.append(
            {
                'item_code': item_code,
                'item_name': str(row.get('item_name') or item.get('itemname') or item.get('ITEMNAME') or item_code),
                'uom': uom,
                'quantity': qty,
                'base_qty': qty,
                'rate': rate,
                'discount': discount,
                'amount': amount,
            }
        )

    delivery_fee = max(_as_float(order.get('delivery_fee')), 0.0)
    delivery_item = _as_int(settings.get('erp_delivery_item_code'))
    if delivery_fee > 0 and delivery_item:
        delivery = get_item_by_code(delivery_item, location_code) or {}
        uom = str(delivery.get('baseuom') or delivery.get('BASEUOM') or 'PCS').strip() or 'PCS'
        lines.append(
            {
                'item_code': delivery_item,
                'item_name': str(delivery.get('itemname') or delivery.get('ITEMNAME') or 'Delivery'),
                'uom': uom,
                'quantity': 1,
                'base_qty': 1,
                'rate': delivery_fee,
                'discount': 0,
                'amount': delivery_fee,
            }
        )

    if not lines:
        return [], 'This order has no invoiceable line items.'
    return lines, None


def create_sales_invoice_for_order(
    order_id: int,
    *,
    created_by: Optional[str] = None,
    updated_by: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a Sales Invoice from one web order. Idempotent if already posted."""
    if not orders_db.orders_tables_ready():
        return {'ok': False, 'error': 'Orders table is not available.'}

    order = orders_db.get_order(int(order_id))
    if not order:
        return {'ok': False, 'error': 'Order not found.'}

    status = str(order.get('order_status') or '').strip().upper()
    if status == 'CANCELLED':
        return {'ok': False, 'error': 'Cancelled orders cannot be invoiced.'}

    loc = _as_int(order.get('location_code')) or resolve_location_code()
    order_number = str(order.get('order_number') or '').strip()
    existing = str(order.get('erp_billno') or '').strip()
    if not existing:
        existing = orders_db.find_invoice_billno_for_order(loc, order_number) or ''
    if existing:
        if not str(order.get('erp_billno') or '').strip():
            orders_db.mark_order_invoiced(
                int(order_id),
                existing,
                updated_by=updated_by,
                created_by_name=created_by,
            )
        return {
            'ok': True,
            'already_invoiced': True,
            'billno': existing,
            'message': f'This order is already invoiced as {existing}.',
        }

    customer_code, customer_name, billing_type = resolve_erp_customer()
    if not customer_code:
        return {
            'ok': False,
            'error': (
                'No ERP customer is set for web invoices. '
                'Open Ecommerce → Settings and enter an ERP customer code (cash customer).'
            ),
        }

    lines, line_err = _invoice_lines(order, loc)
    if line_err:
        return {'ok': False, 'error': line_err}

    buyer = _web_customer_name(order)
    channel = str(order.get('created_by_name') or 'Website').strip() or 'Website'
    remarks_bits = [
        f'{channel} {order_number}',
        str(order.get('fulfillment_type') or '').strip(),
        str(order.get('customer_email') or '').strip(),
    ]
    coupon = str(order.get('coupon_code') or '').strip()
    if coupon:
        remarks_bits.append(f'Coupon {coupon}')
    delivery_fee = max(_as_float(order.get('delivery_fee')), 0.0)
    delivery_item = _as_int(settings_store.load_store_settings().get('erp_delivery_item_code'))
    if delivery_fee > 0 and not delivery_item:
        remarks_bits.append(f'Delivery {order.get("currency_code") or "QAR"} {delivery_fee:.2f} (not invoiced — set delivery item in Settings)')
    notes = str(order.get('customer_notes') or '').strip()
    if notes:
        remarks_bits.append(notes[:180])

    header = {
        'location_code': loc,
        'customercode': customer_code,
        'customername': buyer if buyer else customer_name,
        'customer_billing_type': billing_type or 'CASH',
        'billdate': datetime.now().strftime('%Y-%m-%d'),
        'billtime': datetime.now().strftime('%H:%M:%S'),
        'orderno': order_number[:80],
        'remarks': ' · '.join(bit for bit in remarks_bits if bit)[:240],
        'address': _format_address(order.get('address_snapshot')),
        'createdby': str(created_by or channel or 'ecommerce')[:40],
        'countercode': 0,
    }

    try:
        ok, error, billno, stock_debug = save_sales_invoice({'header': header, 'lines': lines})
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc) or 'Could not save sales invoice.'}

    if not ok or not billno:
        return {'ok': False, 'error': error or 'Could not save sales invoice.'}

    invoice_no = str(billno).strip()
    marked_ok, mark_msg = orders_db.mark_order_invoiced(
        int(order_id),
        invoice_no,
        updated_by=updated_by,
        created_by_name=created_by,
    )
    message = f'Created sales invoice {invoice_no}.'
    if not marked_ok:
        message = f'{message} Invoice saved, but the order link was not stored: {mark_msg}'
    return {
        'ok': True,
        'already_invoiced': False,
        'billno': invoice_no,
        'stock_posted': bool((stock_debug or {}).get('stock_posted')),
        'message': message,
    }
