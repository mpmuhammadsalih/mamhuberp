"""Setup — Approval workflow configuration."""
from pathlib import Path
from nexa_http import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from addons.approval_workflow.approval_workflow_db import (
    TRANSACTION_TYPES,
    build_dashboard_payload,
    delete_workflow,
    get_workflow,
    list_pending,
    queue_action,
    save_delegation,
    save_escalation,
    save_workflow,
    _resolve_location_code,
)

_ADDON = Path(__file__).resolve().parents[1]
bp = Blueprint(
    'approval_workflow',
    __name__,
    url_prefix='/setup',
    template_folder=str(_ADDON / 'views' / 'templates'),
)


def _allowed() -> bool:
    u = (session.get('user') or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    try:
        from permissions import get_role_permissions
        from db import get_user_role_id
        rid = get_user_role_id(session.get('user'))
        if not rid:
            return False
        perms = get_role_permissions(rid) or []
        return 'setup.approval_workflow_page' in perms
    except Exception:
        return False


@bp.route('/approval-workflow', methods=['GET'])
def approval_workflow_page():
    if not session.get('user'):
        return redirect(url_for('auth.login'))
    if not _allowed():
        abort(403)
    loc = _resolve_location_code(session.get('location_code'))
    payload = build_dashboard_payload(loc, session.get('user') or 'web')
    return render_template(
        'approval_workflow/dashboard.html',
        title='Approval Workflow',
        api_url=url_for('approval_workflow.approval_workflow_api_dashboard'),
        save_url=url_for('approval_workflow.approval_workflow_api_save'),
        delete_url_base=url_for('approval_workflow.approval_workflow_api_delete', workflow_id=0).replace('/0', ''),
        action_url=url_for('approval_workflow.approval_workflow_api_queue_action'),
        delegation_url=url_for('approval_workflow.approval_workflow_api_delegation'),
        escalation_url=url_for('approval_workflow.approval_workflow_api_escalation'),
        transaction_types=TRANSACTION_TYPES,
        initial_payload=payload,
    )


@bp.route('/approval-workflow/api/dashboard', methods=['GET'])
def approval_workflow_api_dashboard():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    loc = _resolve_location_code(session.get('location_code'))
    tx_filter = (request.args.get('transaction_type') or 'ALL').strip()
    wf_id = request.args.get('workflow_id')
    payload = build_dashboard_payload(loc, session.get('user') or 'web', tx_filter)
    if wf_id and str(wf_id).isdigit():
        detail = get_workflow(int(wf_id), loc)
        if detail:
            payload['selected_workflow'] = detail
    return jsonify({'success': True, **payload})


@bp.route('/approval-workflow/api/workflow', methods=['POST'])
def approval_workflow_api_save():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    loc = _resolve_location_code(session.get('location_code'))
    wid = data.get('workflow_id')
    try:
        wid_int = int(wid) if wid else None
    except (TypeError, ValueError):
        wid_int = None
    levels = data.get('levels') or []
    ok, err, new_id = save_workflow(
        wid_int,
        loc_code=loc,
        workflow_name=data.get('workflow_name') or '',
        transaction_type=data.get('transaction_type') or '',
        amount_min=float(data.get('amount_min') or 0),
        amount_max=data.get('amount_max'),
        amount_any='Y' if data.get('amount_any') else 'N',
        num_levels=int(data.get('num_levels') or 1),
        status=data.get('status') or 'ACTIVE',
        levels=levels,
        user=session.get('user') or 'web',
    )
    if not ok:
        return jsonify({'success': False, 'error': err}), 400
    detail = get_workflow(int(new_id), loc)
    return jsonify({'success': True, 'workflow_id': new_id, 'workflow': detail})


@bp.route('/approval-workflow/api/workflow/<int:workflow_id>', methods=['DELETE'])
def approval_workflow_api_delete(workflow_id: int):
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    loc = _resolve_location_code(session.get('location_code'))
    ok, err = delete_workflow(workflow_id, loc)
    if not ok:
        return jsonify({'success': False, 'error': err}), 400
    return jsonify({'success': True})


@bp.route('/approval-workflow/api/queue-action', methods=['POST'])
def approval_workflow_api_queue_action():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    try:
        qid = int(data.get('queue_id') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'queue_id required'}), 400
    loc = _resolve_location_code(session.get('location_code'))
    ok, err = queue_action(
        qid, loc, data.get('action') or '', session.get('user') or 'web',
        remarks=data.get('remarks') or '',
    )
    if not ok:
        return jsonify({'success': False, 'error': err}), 400
    payload = build_dashboard_payload(loc, session.get('user') or 'web')
    return jsonify({'success': True, **payload})


@bp.route('/approval-workflow/api/delegation', methods=['POST'])
def approval_workflow_api_delegation():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    loc = _resolve_location_code(session.get('location_code'))
    ok, err = save_delegation(loc, data)
    if not ok:
        return jsonify({'success': False, 'error': err}), 400
    payload = build_dashboard_payload(loc, session.get('user') or 'web')
    return jsonify({'success': True, **payload})


@bp.route('/approval-workflow/api/escalation', methods=['POST'])
def approval_workflow_api_escalation():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    loc = _resolve_location_code(session.get('location_code'))
    ok, err = save_escalation(loc, data)
    if not ok:
        return jsonify({'success': False, 'error': err}), 400
    payload = build_dashboard_payload(loc, session.get('user') or 'web')
    return jsonify({'success': True, **payload})


@bp.route('/approval-workflow/api/pending', methods=['GET'])
def approval_workflow_api_pending():
    if not session.get('user'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if not _allowed():
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    loc = _resolve_location_code(session.get('location_code'))
    return jsonify({'success': True, 'pending': list_pending(loc, 100)})
