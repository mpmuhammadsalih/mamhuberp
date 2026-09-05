"""Transactional email via SMTP (Gmail-compatible)."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple


def smtp_configured() -> bool:
    return bool(os.getenv('SMTP_USER', '').strip() and os.getenv('SMTP_PASSWORD', '').strip())


def send_email(*, to: str, subject: str, html_body: str, text_body: str) -> Tuple[bool, str]:
    """Send one email. Returns (ok, message)."""
    recipient = (to or '').strip()
    if not recipient:
        return False, 'Recipient email is required.'

    host = (os.getenv('SMTP_HOST') or 'smtp.gmail.com').strip()
    port = int(os.getenv('SMTP_PORT') or '587')
    user = os.getenv('SMTP_USER', '').strip()
    password = os.getenv('SMTP_PASSWORD', '').strip()
    from_addr = (os.getenv('SMTP_FROM') or user).strip()
    if not user or not password:
        return False, 'Email is not configured (set SMTP_USER and SMTP_PASSWORD in .env).'

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = recipient
    message.attach(MIMEText(text_body, 'plain', 'utf-8'))
    message.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.sendmail(from_addr, [recipient], message.as_string())
        return True, 'Email sent.'
    except smtplib.SMTPAuthenticationError:
        return False, 'SMTP authentication failed. Use a Gmail App Password, not your account password.'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


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
    return send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
