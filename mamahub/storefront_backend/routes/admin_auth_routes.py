"""Staff admin authentication routes."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from storefront_backend.deps import require_admin
from storefront_backend.services import staff_auth as staff_auth_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/admin/auth', tags=['Admin Authentication'])


class StaffLoginBody(BaseModel):
    email: str
    password: str


@router.post('/login')
def admin_login(payload: StaffLoginBody):
    ok, message, tokens, profile = staff_auth_svc.login_staff(
        email=str(payload.email),
        password=payload.password,
    )
    if not ok or not tokens or not profile:
        raise HTTPException(status_code=401, detail=message)
    return success_response(
        data={'tokens': tokens, 'user': profile},
        message=message,
    )


@router.get('/me')
def admin_me(claims: Annotated[dict, Depends(require_admin)]):
    profile = staff_auth_svc.get_staff_profile(int(claims['sub']))
    if not profile:
        raise HTTPException(status_code=404, detail='User not found')
    return success_response(data=profile, message='Profile retrieved successfully')
