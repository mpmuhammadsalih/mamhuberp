"""Loyalty routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import loyalty as loyalty_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/loyalty', tags=['Loyalty'])


@router.get('/dashboard')
async def loyalty_dashboard(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        data = loyalty_svc.get_dashboard(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(data=data, message='Loyalty dashboard retrieved')


@router.get('/rules')
async def loyalty_rules():
    rule = loyalty_svc.get_active_rule()
    if not rule:
        raise HTTPException(status_code=404, detail='Loyalty program not configured')
    tiers = loyalty_svc.list_tiers()
    return success_response(
        data={'rule': rule, 'tiers': tiers},
        message='Loyalty rules retrieved',
    )
