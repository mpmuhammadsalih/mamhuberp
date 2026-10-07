"""Customer inbox routes — in-app chat + unread badges."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from storefront_backend.deps import customer_user_id, require_customer
from storefront_backend.services import inbox as inbox_svc
from storefront_backend.utils.response import success_response

router = APIRouter(prefix='/inbox', tags=['Inbox'])


class InboxEditBody(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=4000)


class InboxSendBody(BaseModel):
    message_text: str = ''
    conversation_id: Optional[int] = None


def _parse_conversation_id(raw: object) -> Optional[int]:
    if raw in (None, '', False):
        return None
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@router.get('/unread-count')
async def unread_count(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    return success_response(data=inbox_svc.unread_summary(user_id), message='Unread count')


@router.get('/latest')
async def latest_activity(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    return success_response(data=inbox_svc.latest_activity(user_id), message='Latest inbox activity')


@router.get('/conversations')
async def list_conversations(claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    data = inbox_svc.list_conversations(user_id)
    return success_response(data=data, message='Conversations retrieved')


@router.get('/messages')
async def list_messages(
    conversation_id: int = Query(..., gt=0),
    claims: dict = Depends(require_customer),
):
    user_id = customer_user_id(claims)
    try:
        data = inbox_svc.list_messages(user_id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=data, message='Messages retrieved')


@router.get('/files/{filename}')
async def inbox_file(filename: str, claims: dict = Depends(require_customer)):
    customer_user_id(claims)
    path = inbox_svc.inbox_file_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail='File not found')
    return FileResponse(path)


@router.post('/messages')
async def send_message(request: Request, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    content_type = (request.headers.get('content-type') or '').lower()
    message_text = ''
    conversation_id: Optional[int] = None
    image_url = ''
    file_url = ''
    file_name = ''
    file_mime = ''

    if content_type.startswith('application/json'):
        payload = InboxSendBody.model_validate(await request.json())
        message_text = payload.message_text or ''
        conversation_id = _parse_conversation_id(payload.conversation_id)
    else:
        form = await request.form()
        message_text = str(form.get('message_text') or '')
        conversation_id = _parse_conversation_id(form.get('conversation_id'))
        attachment = form.get('attachment')
        if isinstance(attachment, UploadFile) and (attachment.filename or '').strip():
            content = await attachment.read()
            try:
                stored_url, is_image, original, mime = inbox_svc.save_inbox_attachment(
                    attachment.filename or 'attachment',
                    content,
                    attachment.content_type or '',
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if is_image:
                image_url = stored_url
            else:
                file_url = stored_url
                file_name = original
                file_mime = mime

    try:
        data = inbox_svc.send_customer_message(
            user_id,
            message_text,
            conversation_id=conversation_id,
            image_url=image_url,
            file_url=file_url,
            file_name=file_name,
            file_mime=file_mime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(data=data, message='Message sent')


@router.post('/messages/{message_id}/edit')
async def edit_message(message_id: int, payload: InboxEditBody, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        inbox_svc.edit_customer_message(user_id, message_id, payload.message_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(message='Message updated')


@router.post('/messages/{message_id}/delete')
async def delete_message(message_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        inbox_svc.delete_customer_message(user_id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(message='Message deleted')


@router.post('/conversations/{conversation_id}/clear')
async def clear_conversation(conversation_id: int, claims: dict = Depends(require_customer)):
    user_id = customer_user_id(claims)
    try:
        inbox_svc.clear_customer_conversation(user_id, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(message='Chat cleared')
