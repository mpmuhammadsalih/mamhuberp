"""Transaction recording audit — routes and APIs."""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Optional

from nexa_http import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from starlette.responses import FileResponse

from addons.transaction_recording_audit.transaction_recording_audit_db import (
    TRANSACTION_TYPE_FOLDERS,
    TRANSACTION_TYPE_LABELS,
    append_field_change,
    archive_old_audit_files,
    audit_files_root,
    build_dashboard_stats,
    complete_audit_record,
    ensure_auditor_seed_role,
    ensure_transaction_recording_audit_tables,
    get_audit_record,
    list_audit_records,
    list_audit_usernames,
    save_audit_image,
    save_audit_video,
    start_audit_record,
    transaction_view_url,
    user_can_view_recording_audit,
)

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'transaction_recording_audit',
    __name__,
    url_prefix='/audit/recording',
    template_folder=str(_ADDON / 'views' / 'templates'),
)


def _app_root() -> str:
    try:
        from nexa_http import context as ctx
        app = ctx.get_current_app()
        if app and getattr(app.state, 'root_path', None):
            return str(app.state.root_path)
    except Exception:
        pass
    return str(Path(__file__).resolve().parents[2])


def _client_ip() -> str:
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    if forwarded:
        return forwarded[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return ''


def _loc_code() -> int:
    try:
        return int(session.get('location_code') or 1)
    except (TypeError, ValueError):
        return 1


def _recording_capture_enabled() -> bool:
    try:
        from addons.ho.customer_alert_control import get_transaction_recording_enabled
        return get_transaction_recording_enabled('HO')
    except Exception:
        return True


def _require_recording_capture():
    if not _recording_capture_enabled():
        return jsonify({'success': False, 'error': 'Transaction recording is disabled in General Setup.'}, 403)
    return None


def _require_user():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    return None


def _require_auditor():
    denied = _require_user()
    if denied:
        return denied
    if not user_can_view_recording_audit(session.get('user')):
        abort(403)
    return None


def _decode_image_payload(data: dict) -> bytes:
    raw = data.get('image_base64') or data.get('image') or ''
    if isinstance(raw, str) and raw.startswith('data:'):
        raw = raw.split(',', 1)[-1]
    try:
        return base64.b64decode(raw)
    except Exception as exc:
        raise ValueError('Invalid image data') from exc


def _decode_video_payload(data: dict) -> bytes:
    raw = data.get('video_base64') or data.get('video') or ''
    if isinstance(raw, str) and raw.startswith('data:'):
        raw = raw.split(',', 1)[-1]
    try:
        return base64.b64decode(raw)
    except Exception as exc:
        raise ValueError('Invalid video data') from exc


@bp.route('/dashboard')
def dashboard_page():
    denied = _require_auditor()
    if denied:
        return denied
    ensure_transaction_recording_audit_tables()
    return render_template(
        'transaction_recording_audit/dashboard.html',
        title='Transaction Audit Dashboard',
        api_url=url_for('transaction_recording_audit.api_dashboard'),
        viewer_url=url_for('transaction_recording_audit.viewer_page'),
    )


@bp.route('/viewer')
def viewer_page():
    denied = _require_auditor()
    if denied:
        return denied
    ensure_transaction_recording_audit_tables()
    return render_template(
        'transaction_recording_audit/viewer.html',
        title='Transaction Audit Viewer',
        api_list_url=url_for('transaction_recording_audit.api_list'),
        api_users_url=url_for('transaction_recording_audit.api_usernames'),
        replay_url_base=url_for('transaction_recording_audit.replay_page', audit_id=0).replace('/0', '/__ID__'),
        file_url_base=url_for('transaction_recording_audit.serve_file', rel_path='__PATH__').replace('__PATH__', ''),
        dashboard_url=url_for('transaction_recording_audit.dashboard_page'),
        transaction_types=list(TRANSACTION_TYPE_LABELS.items()),
    )


@bp.route('/replay/<int:audit_id>')
def replay_page(audit_id: int):
    denied = _require_auditor()
    if denied:
        return denied
    ensure_transaction_recording_audit_tables()
    record = get_audit_record(audit_id)
    if not record:
        abort(404)
    return render_template(
        'transaction_recording_audit/replay.html',
        title=f'Replay — {record.get("transaction_type_label")} {record.get("transaction_no")}',
        record=record,
        viewer_url=url_for('transaction_recording_audit.viewer_page'),
        file_url_base=url_for('transaction_recording_audit.serve_file', rel_path=''),
    )


@bp.route('/api/dashboard')
def api_dashboard():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not user_can_view_recording_audit(session.get('user')):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    ensure_transaction_recording_audit_tables()
    stats = build_dashboard_stats(location_code=_loc_code())
    stats['success'] = True
    return jsonify(stats)


@bp.route('/api/list')
def api_list():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not user_can_view_recording_audit(session.get('user')):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    ensure_transaction_recording_audit_tables()
    date_from = (request.args.get('date_from') or '').strip()[:10] or None
    date_to = (request.args.get('date_to') or '').strip()[:10] or None
    username = (request.args.get('user') or request.args.get('username') or '').strip() or None
    transaction_type = (request.args.get('transaction_type') or '').strip() or None
    transaction_no = (request.args.get('transaction_no') or '').strip() or None
    try:
        limit = max(20, min(int(request.args.get('limit') or 200), 500))
    except (TypeError, ValueError):
        limit = 200
    rows = list_audit_records(
        date_from=date_from,
        date_to=date_to,
        username=username,
        transaction_type=transaction_type,
        transaction_no=transaction_no,
        location_code=_loc_code(),
        limit=limit,
    )
    for row in rows:
        row['view_transaction_url'] = transaction_view_url(
            row.get('transaction_type') or '',
            row.get('transaction_no') or '',
        )
        row['replay_url'] = url_for('transaction_recording_audit.replay_page', audit_id=row['audit_id'])
    return jsonify({'success': True, 'rows': rows, 'count': len(rows)})


@bp.route('/api/usernames')
def api_usernames():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not user_can_view_recording_audit(session.get('user')):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    ensure_transaction_recording_audit_tables()
    return jsonify({'success': True, 'usernames': list_audit_usernames()})


@bp.route('/api/detail/<int:audit_id>')
def api_detail(audit_id: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    if not user_can_view_recording_audit(session.get('user')):
        return jsonify({'success': False, 'error': 'Forbidden'}, 403)
    ensure_transaction_recording_audit_tables()
    record = get_audit_record(audit_id)
    if not record:
        return jsonify({'success': False, 'error': 'Not found'}, 404)
    record['success'] = True
    record['view_transaction_url'] = transaction_view_url(
        record.get('transaction_type') or '',
        record.get('transaction_no') or '',
    )
    return jsonify(record)


@bp.route('/api/start', methods=['POST'])
def api_start():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    disabled = _require_recording_capture()
    if disabled:
        return disabled
    ensure_transaction_recording_audit_tables()
    data = request.get_json(silent=True) or {}
    tx_type = (data.get('transaction_type') or '').strip()
    tx_no = (data.get('transaction_no') or 'NEW').strip()
    machine_name = (data.get('machine_name') or request.headers.get('X-Machine-Name') or '')[:200]
    try:
        audit_id = start_audit_record(
            transaction_type=tx_type,
            transaction_no=tx_no,
            username=session.get('user') or '',
            ip_address=_client_ip(),
            machine_name=machine_name,
            location_code=_loc_code(),
        )
        return jsonify({'success': True, 'audit_id': audit_id})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/api/field-change', methods=['POST'])
def api_field_change():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    disabled = _require_recording_capture()
    if disabled:
        return disabled
    data = request.get_json(silent=True) or {}
    try:
        audit_id = int(data.get('audit_id') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'audit_id required'}, 400)
    if not audit_id:
        return jsonify({'success': False, 'error': 'audit_id required'}, 400)
    try:
        append_field_change(
            audit_id,
            str(data.get('field_name') or ''),
            data.get('old_value'),
            data.get('new_value'),
        )
        return jsonify({'success': True})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/api/before-screenshot', methods=['POST'])
def api_before_screenshot():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    disabled = _require_recording_capture()
    if disabled:
        return disabled
    data = request.get_json(silent=True) or {}
    try:
        audit_id = int(data.get('audit_id') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'audit_id required'}, 400)
    tx_type = (data.get('transaction_type') or '').strip()
    tx_no = (data.get('transaction_no') or 'NEW').strip()
    try:
        img = _decode_image_payload(data)
        rel = save_audit_image(
            app_root=_app_root(),
            transaction_type=tx_type,
            transaction_no=tx_no,
            image_bytes=img,
            phase='before',
        )
        complete_audit_record(audit_id, status='OPEN', before_image_path=rel)
        return jsonify({'success': True, 'path': rel})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/api/complete', methods=['POST'])
def api_complete():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}, 401)
    disabled = _require_recording_capture()
    if disabled:
        return disabled
    data = request.get_json(silent=True) or {}
    try:
        audit_id = int(data.get('audit_id') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'audit_id required'}, 400)
    tx_type = (data.get('transaction_type') or '').strip()
    tx_no = (data.get('transaction_no') or '').strip()
    status = (data.get('status') or 'SAVED').strip().upper()
    before_path = None
    after_path = None
    video_path = None
    root = _app_root()
    try:
        if data.get('before_image_base64') or data.get('before_image'):
            payload = dict(data)
            payload['image_base64'] = data.get('before_image_base64') or data.get('before_image')
            before_path = save_audit_image(
                app_root=root,
                transaction_type=tx_type,
                transaction_no=tx_no,
                image_bytes=_decode_image_payload(payload),
                phase='before',
            )
        if data.get('after_image_base64') or data.get('after_image'):
            payload = dict(data)
            payload['image_base64'] = data.get('after_image_base64') or data.get('after_image')
            after_path = save_audit_image(
                app_root=root,
                transaction_type=tx_type,
                transaction_no=tx_no,
                image_bytes=_decode_image_payload(payload),
                phase='after',
            )
        video_bytes = None
        if data.get('video_base64') or data.get('video'):
            video_bytes = _decode_video_payload(data)
            if video_bytes and len(video_bytes) > 100:
                ext = (data.get('video_ext') or 'webm').strip()
                video_path = save_audit_video(
                    app_root=root,
                    transaction_type=tx_type,
                    transaction_no=tx_no,
                    video_bytes=video_bytes,
                    ext=ext,
                    audit_id=audit_id,
                )
        complete_audit_record(
            audit_id,
            status=status,
            transaction_no=tx_no or None,
            before_image_path=before_path,
            after_image_path=after_path,
            video_path=video_path,
        )
        return jsonify({
            'success': True,
            'audit_id': audit_id,
            'video_saved': bool(video_path),
            'before_saved': bool(before_path),
            'after_saved': bool(after_path),
        })
    except Exception as exc:
        try:
            complete_audit_record(audit_id, status='FAILED', transaction_no=tx_no or None)
        except Exception:
            pass
        return jsonify({'success': False, 'error': str(exc)}, 500)


@bp.route('/files/<path:rel_path>')
def serve_file(rel_path: str):
    denied = _require_auditor()
    if denied:
        return denied
    clean = re.sub(r'\.\.+', '', (rel_path or '').replace('\\', '/')).strip('/')
    if not clean:
        abort(404)
    root = audit_files_root(_app_root()).resolve()
    target = (root / clean).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        abort(404)
    media = 'application/octet-stream'
    lower = target.suffix.lower()
    if lower == '.png':
        media = 'image/png'
    elif lower in ('.jpg', '.jpeg'):
        media = 'image/jpeg'
    elif lower == '.webp':
        media = 'image/webp'
    elif lower == '.mp4':
        media = 'video/mp4'
    elif lower == '.webm':
        media = 'video/webm'
    return FileResponse(str(target), media_type=media)


def run_startup_maintenance(app_root: Optional[str] = None) -> None:
    """Ensure tables, seed auditor role, archive old files."""
    ensure_transaction_recording_audit_tables()
    try:
        ensure_auditor_seed_role()
    except Exception:
        pass
    try:
        archive_old_audit_files(app_root or _app_root())
    except Exception:
        pass
