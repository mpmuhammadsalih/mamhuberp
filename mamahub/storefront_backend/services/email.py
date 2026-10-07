"""Transactional email — HTTPS first (Gmail web app / Resend / SendGrid), then SMTP."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple

import requests


def smtp_configured() -> bool:
    if os.getenv('GMAIL_WEBAPP_URL', '').strip():
        return True
    if os.getenv('RESEND_API_KEY', '').strip() or os.getenv('SENDGRID_API_KEY', '').strip():
        return True
    return bool(_smtp_user() and os.getenv('SMTP_PASSWORD', '').strip())


def _smtp_user() -> str:
    return (os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER') or '').strip()


def _smtp_from_name() -> str:
    return (os.getenv('SMTP_FROM_NAME') or 'MamaHub').strip()


def _email_only(value: str) -> str:
    text = (value or '').strip()
    if '<' in text and '>' in text:
        return text.split('<', 1)[1].split('>', 1)[0].strip()
    return text


def _format_from(addr: str, name: str = '') -> str:
    email = _email_only(addr)
    display = (name or '').strip()
    if display and email:
        return f'{display} <{email}>'
    return email or addr


def _default_from_addr() -> str:
    addr = (
        os.getenv('SMTP_FROM_EMAIL')
        or os.getenv('SMTP_FROM')
        or _smtp_user()
        or ''
    ).strip()
    return _format_from(addr, _smtp_from_name())


def order_from_email() -> str:
    raw = (
        os.getenv('ORDER_FROM_EMAIL')
        or os.getenv('ORDER_NOTIFY_EMAIL')
        or ''
    ).strip()
    if not raw:
        return _default_from_addr()
    if '<' in raw:
        return raw
    return f'MamaHub <{raw}>'


def _send_via_gmail_webapp(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str = '',
) -> Tuple[bool, str]:
    url = os.getenv('GMAIL_WEBAPP_URL', '').strip()
    if not url:
        return False, 'GMAIL_WEBAPP_URL is not set.'
    payload = {
        'secret': (os.getenv('GMAIL_WEBAPP_SECRET') or '').strip(),
        'to': to,
        'subject': subject,
        'html': html_body,
        'text': text_body,
        'from': (from_addr or _default_from_addr()),
        'name': 'MamaHub',
        'replyTo': (from_addr or _default_from_addr()),
    }
    try:
        session = requests.Session()
        # Apps Script runs doPost on the first hop, then 302s to a GET-only echo URL.
        response = session.post(url, json=payload, timeout=30, allow_redirects=False)
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            nxt = response.headers.get('Location') or ''
            if nxt:
                response = session.get(nxt, timeout=30)
        text = (response.text or '').strip()
        data = {}
        if text.startswith('{'):
            data = response.json()
        if response.ok and (data.get('ok') is True or data.get('success') is True):
            return True, 'Email sent via Gmail web app.'
        if 'doGet' in text or 'doPost' in text:
            return False, (
                'Gmail web app URL is public, but the deployed script has no doGet/doPost. '
                'Paste scripts/gmail_order_mailer.gs in the Apps Script editor, then '
                'Deploy → Manage deployments → pencil → New version → Deploy (Anyone).'
            )
        return False, str(data.get('error') or data.get('message') or text[:200] or f'HTTP {response.status_code}')
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _send_via_resend(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str = '',
) -> Tuple[bool, str]:
    key = os.getenv('RESEND_API_KEY', '').strip()
    if not key:
        return False, 'RESEND_API_KEY is not set.'
    from_addr = (from_addr or _default_from_addr() or 'MamaHub <noreply@mamahub.store>').strip()
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'from': from_addr, 'to': [to], 'subject': subject, 'html': html_body, 'text': text_body},
            timeout=30,
        )
        data = response.json() if response.content else {}
        if response.ok:
            return True, 'Email sent via Resend.'
        return False, str(data.get('message') or data or f'HTTP {response.status_code}')
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _send_via_sendgrid(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str = '',
) -> Tuple[bool, str]:
    key = os.getenv('SENDGRID_API_KEY', '').strip()
    if not key:
        return False, 'SENDGRID_API_KEY is not set.'
    from_addr = (from_addr or _default_from_addr()).strip()
    try:
        response = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'personalizations': [{'to': [{'email': to}]}],
                'from': {'email': from_addr},
                'subject': subject,
                'content': [
                    {'type': 'text/plain', 'value': text_body},
                    {'type': 'text/html', 'value': html_body},
                ],
            },
            timeout=30,
        )
        if response.status_code in (200, 202):
            return True, 'Email sent via SendGrid.'
        return False, response.text or f'HTTP {response.status_code}'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _send_via_smtp(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str = '',
) -> Tuple[bool, str]:
    host = (os.getenv('SMTP_HOST') or 'mail.privateemail.com').strip()
    port = int(os.getenv('SMTP_PORT') or '465')
    user = _smtp_user()
    password = os.getenv('SMTP_PASSWORD', '').strip()
    header_from = _format_from(from_addr or _default_from_addr() or user, _smtp_from_name())
    envelope_from = _email_only(header_from) or user
    if not user or not password:
        return False, 'Email is not configured (set SMTP_USERNAME and SMTP_PASSWORD in .env).'

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = header_from
    message['To'] = to
    message['Reply-To'] = envelope_from
    message.attach(MIMEText(text_body, 'plain', 'utf-8'))
    message.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(user, password)
                server.sendmail(envelope_from, [to], message.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                if port != 25:
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.sendmail(envelope_from, [to], message.as_string())
        return True, 'Email sent.'
    except smtplib.SMTPAuthenticationError:
        return False, 'SMTP authentication failed. Check SMTP_USERNAME and SMTP_PASSWORD.'
    except (TimeoutError, OSError, smtplib.SMTPServerDisconnected) as exc:
        return False, f'SMTP connection failed on {host}:{port} — {exc}'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def send_email(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str = '',
) -> Tuple[bool, str]:
    """Send one email. Returns (ok, message)."""
    recipient = (to or '').strip()
    if not recipient:
        return False, 'Recipient email is required.'
    sender = (from_addr or '').strip()

    if os.getenv('GMAIL_WEBAPP_URL', '').strip():
        return _send_via_gmail_webapp(
            to=recipient, subject=subject, html_body=html_body, text_body=text_body, from_addr=sender,
        )
    if os.getenv('RESEND_API_KEY', '').strip():
        return _send_via_resend(
            to=recipient, subject=subject, html_body=html_body, text_body=text_body, from_addr=sender,
        )
    if os.getenv('SENDGRID_API_KEY', '').strip():
        return _send_via_sendgrid(
            to=recipient, subject=subject, html_body=html_body, text_body=text_body, from_addr=sender,
        )
    return _send_via_smtp(
        to=recipient, subject=subject, html_body=html_body, text_body=text_body, from_addr=sender,
    )


def send_password_reset_email(*, to: str, reset_url: str, first_name: str = '') -> Tuple[bool, str]:
    name = (first_name or '').strip() or 'there'
    subject = 'Reset your MamaHub password'
    text_body = (
        f'Hi {name},\n\n'
        f'We received a request to reset your MamaHub password.\n\n'
        f'Open this link to choose a new password (valid for 1 hour):\n{reset_url}\n\n'
        f'If you did not request this, you can ignore this email.\n\n'
        f'— MamaHub'
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#1a1c2e;max-width:560px;">
      <h2 style="margin:0 0 12px;">Reset your password</h2>
      <p>Hi {name},</p>
      <p>We received a request to reset your MamaHub password.</p>
      <p><a href="{reset_url}" style="display:inline-block;background:#e85d4c;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:bold;">Reset password</a></p>
      <p style="font-size:13px;color:#64748b;">This link expires in 1 hour. If the button does not work, copy and paste this URL into your browser:<br>{reset_url}</p>
      <p style="font-size:13px;color:#64748b;">If you did not request a reset, you can safely ignore this email.</p>
    </div>
    """
    return send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)


def _storefront_base_url() -> str:
    base = (os.getenv('STOREFRONT_BASE_URL') or 'http://localhost:5173').strip().rstrip('/')
    return base or 'http://localhost:5173'


def send_order_confirmation_email(
    *,
    to: str,
    first_name: str,
    order_number: str,
    order_id: int,
    grand_total: float,
    currency_code: str = 'QAR',
    fulfillment_type: str = 'DELIVERY',
    items: list | None = None,
) -> Tuple[bool, str]:
    name = (first_name or '').strip() or 'there'
    order_url = f'{_storefront_base_url()}/orders/{order_id}'
    fulfillment_label = 'Store pickup' if str(fulfillment_type).upper() == 'PICKUP' else 'Delivery'
    total_label = f'{currency_code} {float(grand_total):.2f}'

    lines = items or []
    item_lines_text = '\n'.join(
        f"  • {row.get('item_name') or row.get('item_code')} × {row.get('quantity')} — "
        f"{currency_code} {float(row.get('line_total') or 0):.2f}"
        for row in lines
    )
    item_lines_html = ''.join(
        f"<li style='margin:0 0 6px;'>{row.get('item_name') or row.get('item_code')} "
        f"× {row.get('quantity')} — {currency_code} {float(row.get('line_total') or 0):.2f}</li>"
        for row in lines
    )

    subject = f'Order confirmed — {order_number}'
    text_body = (
        f'Hi {name},\n\n'
        f'Thank you for shopping with MamaHub! Your order is confirmed.\n\n'
        f'Order: {order_number}\n'
        f'Total: {total_label}\n'
        f'Fulfillment: {fulfillment_label}\n'
    )
    if item_lines_text:
        text_body += f'\nItems:\n{item_lines_text}\n'
    text_body += (
        f'\nView your order:\n{order_url}\n\n'
        f'— MamaHub'
    )

    items_html = (
        f"<ul style='margin:8px 0 16px;padding-left:20px;'>{item_lines_html}</ul>"
        if item_lines_html
        else ''
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#1a1c2e;max-width:560px;">
      <h2 style="margin:0 0 12px;">Order confirmed</h2>
      <p>Hi {name},</p>
      <p>Thank you for shopping with MamaHub! Your order is confirmed.</p>
      <div style="margin:16px 0;padding:14px 16px;border-radius:12px;background:#fdf2f8;">
        <p style="margin:0 0 6px;"><strong>{order_number}</strong></p>
        <p style="margin:0 0 6px;">Total: <strong>{total_label}</strong></p>
        <p style="margin:0;">{fulfillment_label}</p>
      </div>
      {items_html}
      <p><a href="{order_url}" style="display:inline-block;background:#e85d4c;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:bold;">View order</a></p>
      <p style="font-size:13px;color:#64748b;">If the button does not work, open: {order_url}</p>
    </div>
    """
    return send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_addr=order_from_email(),
    )


def send_order_status_email(
    *,
    to: str,
    first_name: str,
    order_number: str,
    order_id: int,
    title: str,
    body: str,
) -> Tuple[bool, str]:
    name = (first_name or '').strip() or 'there'
    order_url = f'{_storefront_base_url()}/orders/{order_id}'
    subject = f'{title} — {order_number}'
    text_body = f'Hi {name},\n\n{body}\n\nView your order:\n{order_url}\n\n— MamaHub'
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#1a1c2e;max-width:560px;">
      <h2 style="margin:0 0 12px;">{title}</h2>
      <p>Hi {name},</p>
      <p>{body}</p>
      <p><a href="{order_url}" style="display:inline-block;background:#e85d4c;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:bold;">View order</a></p>
    </div>
    """
    return send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_addr=order_from_email(),
    )


def order_notify_email() -> str:
    return (
        os.getenv('ORDER_NOTIFY_EMAIL')
        or os.getenv('STORE_ORDER_EMAIL')
        or ''
    ).strip()


def send_new_order_staff_email(
    *,
    order_number: str,
    order_id: int,
    grand_total: float,
    currency_code: str = 'QAR',
    fulfillment_type: str = 'DELIVERY',
    customer_name: str = '',
    customer_email: str = '',
    items: list | None = None,
) -> Tuple[bool, str]:
    to = order_notify_email()
    if not to:
        return False, 'ORDER_NOTIFY_EMAIL is not set.'

    fulfillment_label = 'Store pickup' if str(fulfillment_type).upper() == 'PICKUP' else 'Delivery'
    total_label = f'{currency_code} {float(grand_total):.2f}'
    customer = (customer_name or '').strip() or 'Guest'
    customer_line = customer if not customer_email else f'{customer} ({customer_email})'
    erp_url = 'https://erp.mamahub.store/ecommerce/orders'

    lines = items or []
    item_lines_text = '\n'.join(
        f"  • {row.get('item_name') or row.get('item_code')} × {row.get('quantity')} — "
        f"{currency_code} {float(row.get('line_total') or 0):.2f}"
        for row in lines
    )
    item_lines_html = ''.join(
        f"<li style='margin:0 0 6px;'>{row.get('item_name') or row.get('item_code')} "
        f"× {row.get('quantity')} — {currency_code} {float(row.get('line_total') or 0):.2f}</li>"
        for row in lines
    )
    items_html = (
        f"<ul style='margin:8px 0 16px;padding-left:20px;'>{item_lines_html}</ul>"
        if item_lines_html
        else ''
    )

    subject = f'New MamaHub order — {order_number}'
    text_body = (
        f'New storefront order received.\n\n'
        f'Order: {order_number}\n'
        f'Customer: {customer_line}\n'
        f'Total: {total_label}\n'
        f'Fulfillment: {fulfillment_label}\n'
    )
    if item_lines_text:
        text_body += f'\nItems:\n{item_lines_text}\n'
    text_body += f'\nERP orders: {erp_url}\n'

    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#1a1c2e;max-width:560px;">
      <h2 style="margin:0 0 12px;">New order</h2>
      <p>A storefront order was just placed.</p>
      <div style="margin:16px 0;padding:14px 16px;border-radius:12px;background:#fdf2f8;">
        <p style="margin:0 0 6px;"><strong>{order_number}</strong></p>
        <p style="margin:0 0 6px;">Customer: <strong>{customer_line}</strong></p>
        <p style="margin:0 0 6px;">Total: <strong>{total_label}</strong></p>
        <p style="margin:0;">{fulfillment_label}</p>
      </div>
      {items_html}
      <p><a href="{erp_url}" style="display:inline-block;background:#e85d4c;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:bold;">Open in ERP</a></p>
    </div>
    """
    return send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
