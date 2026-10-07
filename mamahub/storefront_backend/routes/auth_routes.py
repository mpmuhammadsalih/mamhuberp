"""Customer auth routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import auth as auth_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/customer/auth', tags=['Customer Authentication'])


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str
    last_name: str
    mobile: str = Field(min_length=8, max_length=20)
    preferred_language: str = 'en'


class UpdateProfileBody(BaseModel):
    mobile: str = Field(min_length=8, max_length=20)


class LoginBody(BaseModel):
    email: EmailStr
    password: str
    guest_cart_token: Optional[str] = None


class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=6)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=10)


@router.post('/register')
def register(payload: RegisterBody):
    ok, message, profile = auth_svc.register_customer(
        email=str(payload.email),
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        mobile=payload.mobile,
        preferred_language=payload.preferred_language,
    )
    if not ok or not profile:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=profile, message=message)


@router.post('/login')
def login(payload: LoginBody):
    ok, message, tokens, profile = auth_svc.login_customer(
        email=str(payload.email),
        password=payload.password,
    )
    if not ok or not tokens or not profile:
        raise HTTPException(status_code=401, detail=message)
    return success_response(
        data={'tokens': tokens, 'user': profile},
        message=message,
    )


@router.post('/refresh')
def refresh_session(payload: RefreshBody):
    ok, message, tokens = auth_svc.refresh_customer_session(payload.refresh_token)
    if not ok or not tokens:
        raise HTTPException(status_code=401, detail=message)
    return success_response(data={'tokens': tokens}, message=message)


@router.get('/me')
def me(claims: dict = Depends(require_customer)):
    profile = auth_svc.get_profile(customer_user_id(claims))
    if not profile:
        raise HTTPException(status_code=404, detail='User not found')
    return success_response(data=profile, message='Profile retrieved successfully')


@router.patch('/me')
def update_me(payload: UpdateProfileBody, claims: dict = Depends(require_customer)):
    ok, message, profile = auth_svc.update_customer_profile(
        user_id=customer_user_id(claims),
        mobile=payload.mobile,
    )
    if not ok or not profile:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=profile, message=message)


@router.post('/forgot-password')
def forgot_password(payload: ForgotPasswordBody):
    ok, message = auth_svc.request_password_reset(email=str(payload.email))
    if not ok:
        raise HTTPException(status_code=503, detail=message)
    return success_response(data={'sent': True}, message=message)


@router.post('/reset-password')
def reset_password(payload: ResetPasswordBody):
    ok, message = auth_svc.reset_password_with_token(
        token=payload.token,
        password=payload.password,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data={'reset': True}, message=message)
