"""Chat routes — colocated under ``addons/chat`` with ``views/templates``."""
from __future__ import annotations
import json
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import List
from nexa_http import Blueprint, Response, current_app, jsonify, redirect, render_template, request
from nexa_http import session, stream_with_context, url_for
from werkzeug.utils import secure_filename
from db import chat_create_group_conversation, chat_delete_message, chat_edit_message, chat_get_conversations, chat_get_messages, chat_get_or_create_direct_conversation, chat_get_typing_users, chat_get_user_sync_token, chat_list_users, chat_send_message, chat_set_typing, chat_share_message_to_user, chat_toggle_reaction, chat_user_can_message_all_tenants, ensure_chat_tables
_ADDON_ROOT = Path(__file__).resolve().parents[1]
bp = Blueprint('chat', __name__, template_folder=str(_ADDON_ROOT / 'views' / 'templates'))
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_FILE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'zip', 'rar', '7z', 'ppt', 'pptx', 'mp4', 'mp3', 'wav', 'webm', 'ogg', 'm4a'}

def _require_login():
    if not session.get('user'):
        return False
    return True

def _current_user() -> str:
    return (session.get('user') or '').strip()

def _to_json_message(row: dict, current_user: str) -> dict:
    return {'message_id': int(row.get('message_id') or 0), 'conversation_id': int(row.get('conversation_id') or 0), 'sender_username': row.get('sender_username') or '', 'message_text': row.get('message_text') or '', 'image_url': row.get('image_url') or '', 'file_url': row.get('file_url') or '', 'file_name': row.get('file_name') or '', 'file_mime': row.get('file_mime') or '', 'replied_message_id': int(row.get('replied_message_id') or 0), 'reply_to_sender': row.get('reply_to_sender') or '', 'reply_to_text': row.get('reply_to_text') or '', 'read_by_all': row.get('read_by_all') or 'N', 'read_count': int(row.get('read_count') or 0), 'reaction_summary': row.get('reaction_summary') or {}, 'my_reaction': row.get('my_reaction') or '', 'edited_flag': row.get('edited_flag') or 'N', 'edited_date': str(row.get('edited_date') or ''), 'created_date': str(row.get('created_date') or ''), 'is_own': (row.get('sender_username') or '').strip().upper() == current_user.strip().upper()}

def _save_attachment_upload(file_storage):
    filename = secure_filename(file_storage.filename or '')
    if not filename:
        raise ValueError('Invalid file name.')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValueError('Unsupported file type.')
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'chat')
    os.makedirs(upload_dir, exist_ok=True)
    new_name = f'{uuid.uuid4().hex}.{ext}'
    full_path = os.path.join(upload_dir, new_name)
    file_storage.save(full_path)
    file_url = f'/static/uploads/chat/{new_name}'
    guessed_mime = mimetypes.guess_type(filename)[0] or (file_storage.mimetype or '')
    is_image = ext in ALLOWED_IMAGE_EXTENSIONS
    return (file_url, is_image, filename, guessed_mime)

@bp.route('/chat', methods=['GET'])
def chat_page():
    if not _require_login():
        return redirect(url_for('auth.login'))
    ensure_chat_tables()
    return render_template('chat/chat.html')

@bp.route('/chat/api/users', methods=['GET'])
def chat_api_users():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    search = (request.args.get('search') or '').strip()
    tenant_id = (session.get('tenant_id') or '').strip() or None
    user = _current_user()
    rows = chat_list_users(user, search=search, tenant_id=tenant_id)
    return jsonify({'ok': True, 'rows': rows, 'all_tenants_users': chat_user_can_message_all_tenants(user)})

@bp.route('/chat/api/conversations', methods=['GET'])
def chat_api_conversations():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    rows = chat_get_conversations(_current_user())
    return jsonify({'ok': True, 'rows': rows})

@bp.route('/chat/api/conversations/direct', methods=['POST'])
def chat_api_conversation_direct():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    target_user = (payload.get('username') or '').strip()
    if not target_user:
        return jsonify({'ok': False, 'error': 'Target user is required.'}, 400)
    tenant_id = (session.get('tenant_id') or '').strip() or None
    try:
        conversation_id = chat_get_or_create_direct_conversation(_current_user(), target_user, tenant_id=tenant_id)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'conversation_id': conversation_id})

@bp.route('/chat/api/conversations/group', methods=['POST'])
def chat_api_conversation_group():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    participants: List[str] = payload.get('participants') or []
    if not isinstance(participants, list):
        participants = []
    tenant_id = (session.get('tenant_id') or '').strip() or None
    try:
        conversation_id = chat_create_group_conversation(_current_user(), title, participants, tenant_id=tenant_id)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'conversation_id': conversation_id})

@bp.route('/chat/api/messages', methods=['GET'])
def chat_api_messages_list():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    try:
        conversation_id = int(request.args.get('conversation_id') or '0')
    except Exception:
        conversation_id = 0
    if conversation_id <= 0:
        return jsonify({'ok': False, 'error': 'conversation_id is required.'}, 400)
    try:
        rows = chat_get_messages(conversation_id, _current_user(), limit=200)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'rows': [_to_json_message(r, _current_user()) for r in rows]})

@bp.route('/chat/api/messages', methods=['POST'])
def chat_api_message_send():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) if request.is_json else {}
    raw_conv = (payload or {}).get('conversation_id')
    if raw_conv is None:
        raw_conv = request.form.get('conversation_id')
    try:
        conversation_id = int(raw_conv or '0')
    except Exception:
        conversation_id = 0
    if conversation_id <= 0:
        return jsonify({'ok': False, 'error': 'conversation_id is required.'}, 400)
    text = ''
    if payload:
        text = (payload.get('message_text') or '').strip()
    else:
        text = (request.form.get('message_text') or '').strip()
    replied_message_id = None
    if payload and payload.get('replied_message_id'):
        replied_message_id = payload.get('replied_message_id')
    elif request.form.get('replied_message_id'):
        replied_message_id = request.form.get('replied_message_id')
    image_url = ''
    file_url = ''
    file_name = ''
    file_mime = ''
    attachment_file = request.files.get('attachment') or request.files.get('image')
    if attachment_file and (attachment_file.filename or '').strip():
        try:
            saved_url, is_image, original_name, mime_type = _save_attachment_upload(attachment_file)
            if is_image:
                image_url = saved_url
            else:
                file_url = saved_url
                file_name = original_name
                file_mime = mime_type
        except Exception as exc:
            return jsonify({'ok': False, 'error': str(exc)}, 400)
    try:
        row = chat_send_message(conversation_id, _current_user(), text, image_url, file_url=file_url, file_name=file_name, file_mime=file_mime, replied_message_id=replied_message_id)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'row': _to_json_message(row, _current_user())})

@bp.route('/chat/api/messages/<int:message_id>/edit', methods=['POST'])
def chat_api_message_edit(message_id: int):
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    message_text = (payload.get('message_text') or '').strip()
    if not message_text:
        return jsonify({'ok': False, 'error': 'message_text is required.'}, 400)
    try:
        updated = chat_edit_message(message_id, _current_user(), message_text)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    if not updated:
        return jsonify({'ok': False, 'error': 'Message not found or not editable.'}, 404)
    return jsonify({'ok': True})

@bp.route('/chat/api/messages/<int:message_id>/delete', methods=['POST'])
def chat_api_message_delete(message_id: int):
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    try:
        deleted = chat_delete_message(message_id, _current_user())
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    if not deleted:
        return jsonify({'ok': False, 'error': 'Message not found or not deletable.'}, 404)
    return jsonify({'ok': True})

@bp.route('/chat/api/stream', methods=['GET'])
def chat_api_stream():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    current_user = _current_user()

    @stream_with_context
    def event_stream():
        last_token = ''
        for _ in range(300):
            token = chat_get_user_sync_token(current_user)
            if token != last_token:
                last_token = token
                payload = json.dumps({'token': token, 'ts': int(time.time())})
                yield f'event: sync\ndata: {payload}\n\n'
            else:
                yield 'event: ping\ndata: {}\n\n'
            time.sleep(1)
    resp = Response(event_stream(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@bp.route('/chat/api/messages/<int:message_id>/react', methods=['POST'])
def chat_api_message_react(message_id: int):
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    reaction = (payload.get('reaction') or 'LIKE').strip().upper()
    try:
        result = chat_toggle_reaction(message_id, _current_user(), reaction=reaction)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'result': result})

@bp.route('/chat/api/messages/<int:message_id>/share', methods=['POST'])
def chat_api_message_share(message_id: int):
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    target_user = (payload.get('username') or '').strip()
    usernames = payload.get('usernames') or []
    note = (payload.get('note') or '').strip()
    targets: List[str] = []
    if isinstance(usernames, list):
        for v in usernames:
            s = str(v or '').strip()
            if s:
                targets.append(s)
    if target_user:
        targets.append(target_user)
    deduped: List[str] = []
    seen = set()
    for t in targets:
        k = t.upper()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(t)
    if not deduped:
        return jsonify({'ok': False, 'error': 'At least one target user is required.'}, 400)
    rows = []
    failed = []
    for tu in deduped:
        try:
            row = chat_share_message_to_user(message_id, _current_user(), tu, note=note)
            rows.append(_to_json_message(row, _current_user()))
        except Exception as exc:
            failed.append({'username': tu, 'error': str(exc)})
    if not rows:
        return jsonify({'ok': False, 'error': 'Share failed for all selected users.', 'failed': failed}, 400)
    return jsonify({'ok': True, 'rows': rows, 'failed': failed, 'sent_count': len(rows)})

@bp.route('/chat/api/typing', methods=['POST'])
def chat_api_typing_set():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    payload = request.get_json(silent=True) or {}
    try:
        conversation_id = int(payload.get('conversation_id') or 0)
    except Exception:
        conversation_id = 0
    is_typing = bool(payload.get('is_typing'))
    if conversation_id <= 0:
        return jsonify({'ok': False, 'error': 'conversation_id is required.'}, 400)
    try:
        chat_set_typing(conversation_id, _current_user(), is_typing)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True})

@bp.route('/chat/api/typing', methods=['GET'])
def chat_api_typing_get():
    if not _require_login():
        return jsonify({'ok': False, 'error': 'Unauthorized'}, 401)
    try:
        conversation_id = int(request.args.get('conversation_id') or 0)
    except Exception:
        conversation_id = 0
    if conversation_id <= 0:
        return jsonify({'ok': False, 'error': 'conversation_id is required.'}, 400)
    try:
        rows = chat_get_typing_users(conversation_id, _current_user())
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}, 400)
    return jsonify({'ok': True, 'rows': rows})
