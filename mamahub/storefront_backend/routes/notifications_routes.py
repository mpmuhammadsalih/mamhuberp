"""Notification routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import notifications as notification_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/notifications', tags=['Notifications'])


@router.get('')
async def list_notifications(
    claims: dict = Depends(require_customer),
    unread_only: bool = Query(False),
):
    user_id = customer_user_id(claims)
    data = notification_svc.list_for_user(user_id, unread_only=unread_only)
    return success_response(data=data, message='Notifications retrieved')


@router.get('/unread-count')
async def unread_count(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    count = notification_svc.unread_count(user_id)
    return success_response(data={'count': count}, message='Unread count')


@router.post('/{notification_id}/read')
async def mark_read(notification_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    notification_svc.mark_read(user_id, notification_id)
    return success_response(message='Notification marked read')


@router.post('/read-all')
async def mark_all_read(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    notification_svc.mark_all_read(user_id)
    return success_response(message='All notifications marked read')
