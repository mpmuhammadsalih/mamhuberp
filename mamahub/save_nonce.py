"""App-wide replay protection for save/submit actions (signed session, one-time token).

Use ``get_or_issue_global_save_nonce()`` in a context processor so ``base.html`` can
set ``window.__GLOBAL_SAVE_NONCE``. The fetch wrapper in ``base.html`` merges this into
JSON POST/PUT/PATCH bodies and refreshes it from JSON responses that include ``save_nonce``.

On the server, validate with ``verify_consume_save_nonce(...)`` and rotate with
``json_response_rotate_global()``. New JSON save endpoints should follow this pattern.
Replay uses the signed session; use a shared session store for multi-worker setups
if strict exactly-once semantics are required.
"""
from __future__ import annotations
import uuid
from functools import wraps
from typing import Any, Dict, Optional
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse
from nexa_http import jsonify, request, session
GLOBAL_SAVE_NONCE_SESSION_KEY = 'app_global_save_nonce_v1'
POS_SAVE_NONCE_SESSION_KEY = 'app_pos_save_nonce_v1'


def _pos_counter_code_for_nonce() -> int:
    try:
        return int(session.get('countercode') or 0)
    except (TypeError, ValueError):
        return 0


def pos_save_nonce_session_key(counter_code: Any = None) -> str:
    """Per-counter POS token so multiple counters/tabs do not share one one-time nonce."""
    if counter_code is None:
        counter_code = _pos_counter_code_for_nonce()
    try:
        cc = int(counter_code or 0)
    except (TypeError, ValueError):
        cc = 0
    if cc > 0:
        return f'{POS_SAVE_NONCE_SESSION_KEY}_c{cc}'
    return POS_SAVE_NONCE_SESSION_KEY


def _clear_pos_save_nonce_keys() -> None:
    for key in list(session.keys()):
        sk = str(key)
        if sk == POS_SAVE_NONCE_SESSION_KEY or sk.startswith(f'{POS_SAVE_NONCE_SESSION_KEY}_'):
            session.pop(key, None)

# Kept when resetting ephemeral session state after New Company / data wipe.
_PRESERVE_SESSION_KEYS = frozenset({
    'user',
    'employeecode',
    'tenant_id',
    'location_code',
    'location_name',
})


def clear_ephemeral_session_state(*, reissue_save_nonces: bool = True) -> tuple[int, list[str]]:
    """
    Remove stale locks, save tokens, POS counter context, and form once-keys from the
    current browser session. Login user, tenant, and branch selection are preserved.

    Call after truncating business data so saves (GRN, sales, POS, etc.) do not hit
    replay-blocked errors from pre-wipe session state.
    """
    cleared: list[str] = []
    for key in list(session.keys()):
        if key in _PRESERVE_SESSION_KEYS:
            continue
        session.pop(key, None)
        cleared.append(str(key))
    if reissue_save_nonces and session.get('user'):
        issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
        _clear_pos_save_nonce_keys()
        issue_save_nonce(pos_save_nonce_session_key())
    session.modified = True
    return (len(cleared), cleared)

def issue_save_nonce(session_key: str) -> str:
    n = uuid.uuid4().hex
    session[session_key] = n
    session.modified = True
    return n

def verify_consume_save_nonce(session_key: str, submitted: Optional[str]) -> bool:
    return consume_save_nonce(session_key, submitted)


def peek_save_nonce(session_key: str, submitted: Optional[str]) -> bool:
    """Check token without consuming (for form validation before commit)."""
    expected = session.get(session_key)
    got = (submitted or '').strip()
    return bool(expected and got and got == expected)


def consume_save_nonce(session_key: str, submitted: Optional[str]) -> bool:
    if not peek_save_nonce(session_key, submitted):
        return False
    session.pop(session_key, None)
    session.modified = True
    return True


def reject_invalid_form_save_nonce(submitted: Optional[str], *, session_key: str = GLOBAL_SAVE_NONCE_SESSION_KEY) -> bool:
    """Return True when the posted token matches the session. On failure, issue a fresh token."""
    if peek_save_nonce(session_key, submitted):
        return True
    issue_save_nonce(session_key)
    return False


def commit_form_save_nonce(submitted: Optional[str], *, session_key: str = GLOBAL_SAVE_NONCE_SESSION_KEY) -> bool:
    """Consume the one-time token after validation passed and before DB commit."""
    return consume_save_nonce(session_key, submitted)

def get_or_issue_global_save_nonce() -> str:
    if not session.get('user'):
        return ''
    sk = GLOBAL_SAVE_NONCE_SESSION_KEY
    v = session.get(sk)
    if not v:
        v = issue_save_nonce(sk)
    return v


def get_or_issue_pos_save_nonce() -> str:
    if not session.get('user'):
        return ''
    sk = pos_save_nonce_session_key()
    v = session.get(sk)
    if not v:
        v = issue_save_nonce(sk)
    return v


def reject_invalid_pos_save_nonce(submitted: Optional[str]) -> bool:
    return reject_invalid_form_save_nonce(submitted, session_key=pos_save_nonce_session_key())


def commit_pos_save_nonce(submitted: Optional[str]) -> bool:
    return commit_form_save_nonce(submitted, session_key=pos_save_nonce_session_key())


def json_response_rotate_pos(body: Dict[str, Any], status: int = 200) -> JSONResponse:
    merged = dict(body)
    merged['save_nonce'] = issue_save_nonce(pos_save_nonce_session_key())
    return JSONResponse(content=jsonable_encoder(merged), status_code=status)


def replay_blocked_response_pos() -> JSONResponse:
    sk = pos_save_nonce_session_key()
    cur = session.get(sk)
    if not cur:
        cur = issue_save_nonce(sk)
    return JSONResponse(
        content=jsonable_encoder(
            {
                'success': False,
                'error': 'Duplicate or invalid save request. This can happen if Save was already processed, the page was opened in another tab, or the session expired. Use the new save token and try again.',
                'replay_blocked': True,
                'save_nonce': cur,
            }
        ),
        status_code=409,
    )


def refresh_pos_save_nonce() -> str:
    """Issue a fresh POS save token for the active counter (client refresh / bind counter)."""
    return issue_save_nonce(pos_save_nonce_session_key())

def extract_submitted_save_nonce(req) -> str:
    v = req.headers.get('X-Save-Nonce') or req.headers.get('Save-Nonce') or ''
    if v.strip():
        return v.strip()
    if req.is_json:
        body = req.get_json(silent=True)
        if isinstance(body, dict):
            return str(body.get('save_nonce') or '').strip()
    if req.form:
        return str(req.form.get('save_nonce') or '').strip()
    return ''

def json_response_rotate_global(body: Dict[str, Any], status: int=200) -> JSONResponse:
    merged = dict(body)
    merged['save_nonce'] = issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return JSONResponse(content=jsonable_encoder(merged), status_code=status)


def json_response_keep_global_nonce(body: Dict[str, Any], status: int = 400) -> JSONResponse:
    """Return JSON without rotating the save token (failed validation/save — client may retry once)."""
    merged = dict(body)
    cur = session.get(GLOBAL_SAVE_NONCE_SESSION_KEY)
    if cur:
        merged['save_nonce'] = cur
    return JSONResponse(content=jsonable_encoder(merged), status_code=status)

def replay_blocked_response_global() -> JSONResponse:
    cur = session.get(GLOBAL_SAVE_NONCE_SESSION_KEY)
    if not cur:
        cur = issue_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY)
    return JSONResponse(content=jsonable_encoder({'success': False, 'error': 'Duplicate or invalid save request. This can happen if Save was already processed, the page was opened in another tab, or the session expired. Use the new save token and try again.', 'replay_blocked': True, 'save_nonce': cur}), status_code=409)

def require_global_save_nonce(view_fn):
    """Consume one-time token from JSON body, form, or ``X-Save-Nonce`` header. Return JSON responses via ``json_response_rotate_global``."""

    @wraps(view_fn)
    def wrapped(*args, **kwargs):
        if not session.get('user'):
            return jsonify({'success': False, 'error': 'Not authenticated'}, 401)
        submitted = extract_submitted_save_nonce(request)
        if not verify_consume_save_nonce(GLOBAL_SAVE_NONCE_SESSION_KEY, submitted):
            return replay_blocked_response_global()
        return view_fn(*args, **kwargs)
    return wrapped
