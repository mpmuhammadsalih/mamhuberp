"""FastAPI dependencies for save-once (replay) protection.

New mutation routes: add ``require_save_nonce`` + return ``success_after_mutation(...)``.
See ``mobile_backend/MUTATIONS.md``.
"""
from __future__ import annotations

from fastapi import Depends, Request

from mobile_backend.jwt_compat import jwt_identity
from mobile_backend.request_context import get_jwt
from mobile_backend.save_guard import (
    commit_save_nonce,
    reject_invalid_save_nonce,
    rotate_save_nonce,
)
from mobile_backend.utils.response import success


class SaveNonceReplayError(Exception):
    def __init__(self, save_nonce: str, message: str | None = None):
        self.save_nonce = save_nonce
        self.message = message or (
            "Duplicate or invalid save request. This can happen if Save was already processed, "
            "the request was sent twice, or the session expired. Use the new save token and try again."
        )


def extract_save_nonce(request: Request) -> str:
    header = request.headers.get("X-Save-Nonce") or request.headers.get("Save-Nonce") or ""
    return header.strip()


def validate_save_nonce(request: Request) -> None:
    claims = get_jwt()
    username = jwt_identity(claims)
    tenant_id = str(claims.get("tenant_id") or "")
    submitted = extract_save_nonce(request)
    ok, current = reject_invalid_save_nonce(username, tenant_id, submitted)
    if not ok:
        raise SaveNonceReplayError(current)
    request.state.save_nonce_submitted = submitted
    request.state.save_nonce_user = username
    request.state.save_nonce_tenant = tenant_id


require_save_nonce = Depends(validate_save_nonce)


def finalize_save_nonce(request: Request) -> str:
    username = getattr(request.state, "save_nonce_user", "")
    tenant_id = getattr(request.state, "save_nonce_tenant", "")
    submitted = getattr(request.state, "save_nonce_submitted", "")
    commit_save_nonce(username, tenant_id, submitted)
    return rotate_save_nonce(username, tenant_id)


def success_after_mutation(request: Request, data=None, message: str = "OK", status_code: int = 200):
    nonce = finalize_save_nonce(request)
    return success(data, message=message, status_code=status_code, save_nonce=nonce)
