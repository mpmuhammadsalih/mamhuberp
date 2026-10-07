"""Shop inbox — same chat tables as staff /chat, plus in-app notifications."""
from __future__ import annotations

import mimetypes
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _chat_user_exists,
    _is_shop_customer_chat_user,
    _safe_rows_auth,
    chat_customer_username,
    chat_get_conversations,
    chat_get_messages,
    chat_get_or_create_direct_conversation,
    chat_clear_conversation,
    chat_delete_message,
    chat_edit_message,
    chat_send_message,
    chat_shop_customer_id_for_conversation,
)
from storefront_backend.services import notifications as notification_svc

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_FILE_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx',
    'csv', 'txt', 'zip', 'rar', '7z', 'ppt', 'pptx', 'mp4', 'mp3', 'wav',
    'webm', 'ogg', 'm4a',
}
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
CHAT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / 'static' / 'uploads' / 'chat'
_SAFE_FILE_NAME = re.compile(r'^[a-fA-F0-9]{32}\.[A-Za-z0-9]{1,8}$')


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def resolve_support_staff_username() -> Optional[str]:
    env_name = (os.getenv('SUPPORT_CHAT_USERNAME') or '').strip()
    if env_name and _chat_user_exists(env_name) and not _is_shop_customer_chat_user(env_name):
        return env_name
    rows = _safe_rows_auth(
        """
        SELECT username FROM (
            SELECT username
            FROM login_users
            WHERE UPPER(NVL(TRIM(active_flag), 'Y')) = 'Y'
            ORDER BY username
        ) WHERE ROWNUM = 1
        """,
        {},
    )
    if not rows:
        return None
    name = str(rows[0].get('username') or '').strip()
    return name or None


def chat_unread_count(user_id: int) -> int:
    rows = chat_get_conversations(chat_customer_username(user_id))
    return sum(int(row.get('unread_count') or 0) for row in rows)


def unread_summary(user_id: int) -> Dict[str, int]:
    try:
        chat = chat_unread_count(user_id)
    except Exception:
        chat = 0
    alerts = notification_svc.unread_count(user_id)
    return {'chat': chat, 'notifications': alerts, 'total': chat + alerts}


def latest_activity(user_id: int) -> Dict[str, Any]:
    unread = unread_summary(user_id)
    notification = None
    rows = notification_svc.list_for_user(user_id, unread_only=False, limit=1)
    if rows:
        row = rows[0]
        notification = {
            'notification_id': int(row.get('notification_id') or 0),
            'title': row.get('title') or 'MamaHub',
            'body': row.get('body') or '',
            'notification_type': row.get('notification_type') or '',
            'is_read': bool(row.get('is_read')),
        }
    chat = None
    try:
        convos = list_conversations(user_id)
    except Exception:
        convos = []
    if convos:
        top = convos[0]
        chat = {
            'conversation_id': int(top.get('conversation_id') or 0),
            'last_text': top.get('last_text') or '',
            'updated_at': top.get('updated_at'),
            'unread_count': int(top.get('unread_count') or 0),
        }
    return {
        'unread': unread,
        'notification': notification,
        'chat': chat,
    }


def inbox_file_path(filename: str) -> Optional[Path]:
    name = (filename or '').strip()
    if not _SAFE_FILE_NAME.match(name):
        return None
    path = (CHAT_UPLOAD_DIR / name).resolve()
    try:
        path.relative_to(CHAT_UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def public_inbox_file_url(url: Optional[str]) -> str:
    raw = (url or '').strip()
    if not raw:
        return ''
    name = raw.rsplit('/', 1)[-1]
    if not _SAFE_FILE_NAME.match(name):
        return raw
    return f'/api/v1/inbox/files/{name}'


def _preview_text(row: Dict[str, Any]) -> str:
    text = (row.get('last_text') or '').strip()
    if text:
        return text
    if row.get('last_image_url'):
        return '[Photo]'
    name = (row.get('last_file_name') or '').strip()
    if name:
        lower = name.lower()
        if lower.endswith(('.webm', '.ogg', '.wav', '.mp3', '.m4a')):
            return '[Voice note]'
        return f'[File] {name}'
    return ''


def _serialize_message(row: Dict[str, Any], *, uname: str, fallback_text: str = '') -> Dict[str, Any]:
    sender = str(row.get('sender_username') or '').strip()
    is_own = sender.upper() == uname.upper()
    image_url = public_inbox_file_url(row.get('image_url'))
    file_url = public_inbox_file_url(row.get('file_url'))
    return {
        'message_id': int(row.get('message_id') or 0),
        'conversation_id': int(row.get('conversation_id') or 0),
        'is_own': is_own,
        'from_support': not is_own,
        'message_text': row.get('message_text') or fallback_text,
        'image_url': image_url or None,
        'file_url': file_url or None,
        'file_name': row.get('file_name') or None,
        'file_mime': row.get('file_mime') or None,
        'edited': str(row.get('edited_flag') or 'N').upper() == 'Y',
        'created_at': _iso(row.get('created_date')),
    }


def save_inbox_attachment(filename: str, content: bytes, mime: str = '') -> Tuple[str, bool, str, str]:
    if not content:
        raise ValueError('Attachment is empty.')
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError('Attachment is too large (max 15 MB).')
    original = (filename or 'attachment').strip() or 'attachment'
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValueError('Unsupported file type.')
    CHAT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = f'{uuid.uuid4().hex}.{ext}'
    path = CHAT_UPLOAD_DIR / stored
    path.write_bytes(content)
    guessed = mime or (mimetypes.guess_type(original)[0] or '')
    return (f'/static/uploads/chat/{stored}', ext in ALLOWED_IMAGE_EXTENSIONS, original[:255], guessed[:120])


def list_conversations(user_id: int) -> List[Dict[str, Any]]:
    uname = chat_customer_username(user_id)
    out: List[Dict[str, Any]] = []
    for row in chat_get_conversations(uname):
        out.append(
            {
                'conversation_id': int(row.get('conversation_id') or 0),
                'display_name': 'MamaHub',
                'last_text': _preview_text(row),
                'unread_count': int(row.get('unread_count') or 0),
                'updated_at': _iso(row.get('updated_date') or row.get('last_created_date')),
            }
        )
    return out


def list_messages(user_id: int, conversation_id: int) -> List[Dict[str, Any]]:
    uname = chat_customer_username(user_id)
    rows = chat_get_messages(int(conversation_id), uname, limit=200)
    return [_serialize_message(row, uname=uname) for row in rows]


def open_support_conversation(user_id: int) -> int:
    staff = resolve_support_staff_username()
    if not staff:
        raise ValueError('Support chat is not available yet.')
    return chat_get_or_create_direct_conversation(chat_customer_username(user_id), staff)


def send_customer_message(
    user_id: int,
    message_text: str,
    conversation_id: Optional[int] = None,
    *,
    image_url: str = '',
    file_url: str = '',
    file_name: str = '',
    file_mime: str = '',
) -> Dict[str, Any]:
    text = (message_text or '').strip()
    if not text and not image_url and not file_url:
        raise ValueError('Message text or attachment is required.')
    cid = int(conversation_id or 0)
    if cid <= 0:
        cid = open_support_conversation(user_id)
    uname = chat_customer_username(user_id)
    row = chat_send_message(
        cid,
        uname,
        text,
        image_url=image_url,
        file_url=file_url,
        file_name=file_name,
        file_mime=file_mime,
    )
    return _serialize_message(row, uname=uname, fallback_text=text)


def edit_customer_message(user_id: int, message_id: int, message_text: str) -> None:
    text = (message_text or '').strip()
    if not text:
        raise ValueError('Message cannot be empty.')
    updated = chat_edit_message(int(message_id), chat_customer_username(user_id), text)
    if not updated:
        raise ValueError('Message not found or not editable.')


def delete_customer_message(user_id: int, message_id: int) -> None:
    deleted = chat_delete_message(int(message_id), chat_customer_username(user_id))
    if not deleted:
        raise ValueError('Message not found or not deletable.')


def clear_customer_conversation(user_id: int, conversation_id: int) -> int:
    return chat_clear_conversation(int(conversation_id), chat_customer_username(user_id))


def send_in_app_notification(user_id: int, message: str, *, title: str = 'Message from MamaHub') -> Optional[int]:
    body = (message or '').strip()
    if not body:
        raise ValueError('Message text is required.')
    notification_id = notification_svc.create_notification(
        user_id=int(user_id),
        notification_type='ASSIST',
        title=title[:200],
        body=body[:2000],
        ref_entity='ASSIST',
    )
    if not notification_id:
        raise RuntimeError('Could not save the in-app notification.')
    return notification_id


def open_staff_customer_chat(staff_username: str, user_id: int, message: str) -> int:
    staff = (staff_username or '').strip()
    if not staff:
        raise ValueError('Staff user is required.')
    text = (message or '').strip()
    cid = chat_get_or_create_direct_conversation(staff, chat_customer_username(user_id))
    if text:
        chat_send_message(cid, staff, text)
        notify_customer_of_staff_message(cid, text, staff)
    return cid


def notify_customer_of_staff_message(
    conversation_id: int,
    message_text: str,
    sender_username: str,
) -> None:
    if _is_shop_customer_chat_user(sender_username):
        return
    user_id = chat_shop_customer_id_for_conversation(conversation_id)
    if not user_id:
        return
    body = (message_text or '').strip() or 'MamaHub sent you a message.'
    notification_svc.create_notification(
        user_id=user_id,
        notification_type='ASSIST_CHAT',
        title='New message from MamaHub',
        body=body[:2000],
        ref_entity='CHAT',
        ref_entity_id=int(conversation_id),
    )


def parse_assist_user_id(raw: Any) -> Tuple[Optional[int], str]:
    try:
        user_id = int(raw or 0)
    except (TypeError, ValueError):
        user_id = 0
    if user_id <= 0:
        return None, 'Customer account is required for in-app chat.'
    if not _shop_customer_exists_id(user_id):
        return None, 'Customer not found.'
    return user_id, ''


def _shop_customer_exists_id(user_id: int) -> bool:
    from db import _safe_rows, _table_exists

    if not _table_exists('APP_USER'):
        return False
    rows = _safe_rows('SELECT USER_ID FROM APP_USER WHERE USER_ID = :id', {'id': int(user_id)})
    return bool(rows)
