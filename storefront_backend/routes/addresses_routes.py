"""Customer address routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import addresses as address_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/addresses', tags=['Addresses'])


class AddressCreateBody(BaseModel):
    address_title: str = Field(min_length=1, max_length=100)
    address_type: str = Field(default='HOME', pattern='^(HOME|OFFICE|OTHER)$')
    building_number: Optional[str] = Field(default=None, max_length=50)
    street: str = Field(min_length=1, max_length=200)
    zone: Optional[str] = Field(default=None, max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    country: str = Field(default='Qatar', max_length=100)
    landmark: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool = False


class AddressUpdateBody(BaseModel):
    address_title: Optional[str] = Field(default=None, max_length=100)
    address_type: Optional[str] = Field(default=None, pattern='^(HOME|OFFICE|OTHER)$')
    building_number: Optional[str] = Field(default=None, max_length=50)
    street: Optional[str] = Field(default=None, max_length=200)
    zone: Optional[str] = Field(default=None, max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    country: Optional[str] = Field(default=None, max_length=100)
    landmark: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: Optional[bool] = None


@router.get('')
async def list_addresses(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = address_svc.list_addresses(user_id)
    return success_response(data=data, message='Addresses retrieved successfully')


@router.post('')
async def create_address(payload: AddressCreateBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message, data = address_svc.create_address(user_id, payload.model_dump())
    if not ok or not data:
        raise HTTPException(status_code=400, detail=message)
    return success_response(data=data, message='Address created successfully')


@router.patch('/{address_id}')
async def update_address(
    address_id: int,
    payload: AddressUpdateBody,
    claims: dict = Depends(require_customer),
):
    user_id = customer_user_id(claims)
    updates = payload.model_dump(exclude_unset=True)
    ok, message, data = address_svc.update_address(user_id, address_id, updates)
    if not ok or not data:
        status = 404 if message == 'Address not found' else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(data=data, message='Address updated successfully')


@router.delete('/{address_id}')
async def delete_address(address_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message = address_svc.delete_address(user_id, address_id)
    if not ok:
        status = 404 if message == 'Address not found' else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(message='Address deleted successfully')


@router.post('/{address_id}/default')
async def set_default_address(address_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    ok, message, data = address_svc.set_default_address(user_id, address_id)
    if not ok or not data:
        status = 404 if message == 'Address not found' else 400
        raise HTTPException(status_code=status, detail=message)
    return success_response(data=data, message='Default address updated')
