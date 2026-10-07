from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str
    permissions: List[str]


class AgentOut(BaseModel):
    user_id: int
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    user_id: int
    username: str
    email: Optional[str] = None
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}

    @field_validator("is_active", mode="before")
    @classmethod
    def coerce_active(cls, value):
        if isinstance(value, bool):
            return value
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return bool(value)


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None
    role: str = "SALES"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
