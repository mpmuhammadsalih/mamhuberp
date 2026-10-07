from __future__ import annotations

from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.exceptions import UnauthorizedError
from app.core.permissions import Permission, permissions_for
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.database.session import get_db
from app.models.user import User
from app.schemas.auth import AgentOut, LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")
    user.last_login_at = datetime.utcnow()
    write_audit(
        db,
        action="login",
        user_id=user.user_id,
        entity_type="user",
        entity_id=str(user.user_id),
        ip_address=request.client.host if request.client else None,
    )
    return _token_response(user)


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role, user.username),
        refresh_token=create_refresh_token(user.user_id),
        role=user.role,
        username=user.username,
        full_name=user.full_name,
        permissions=sorted(permissions_for(user.role)),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    try:
        data = decode_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise UnauthorizedError("Session expired. Please sign in again.") from exc
    if data.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")
    try:
        user_id = int(data.get("sub") or 0)
    except (TypeError, ValueError):
        user_id = 0
    user = db.get(User, user_id) if user_id else None
    if not user or int(user.is_active or 0) != 1:
        raise UnauthorizedError("User is inactive or missing")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@users_router.get("", response_model=List[UserOut])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))],
) -> List[User]:
    return db.query(User).order_by(User.full_name.asc()).all()


@users_router.get("/agents", response_model=List[AgentOut])
def list_agents(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CHATS_MANAGE))],
) -> List[User]:
    return (
        db.query(User)
        .filter(User.is_active == 1)
        .order_by(User.full_name.asc())
        .all()
    )


@users_router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))],
) -> User:
    user = User(
        username=payload.username.strip(),
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=1,
    )
    db.add(user)
    db.flush()
    write_audit(db, action="user.create", user_id=actor.user_id, entity_type="user", entity_id=str(user.user_id))
    return user


@users_router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))],
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise UnauthorizedError("User not found")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if "is_active" in data:
        data["is_active"] = 1 if data["is_active"] else 0
    for key, value in data.items():
        setattr(user, key, value)
    if password:
        user.password_hash = hash_password(password)
    write_audit(db, action="user.update", user_id=actor.user_id, entity_type="user", entity_id=str(user_id))
    return user
