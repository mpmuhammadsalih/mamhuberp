"""Storefront content routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from addons.ecommerce.services import media as media_svc
from storefront_backend.services import storefront as storefront_svc
from storefront_backend.utils.response import success_response

router = APIRouter(tags=['Storefront'])


@router.get('/storefront/home')
async def storefront_home(response: Response):
    data = storefront_svc.get_storefront_home()
    response.headers['Cache-Control'] = 'public, max-age=300, must-revalidate'
    return success_response(data=data, message='Storefront home content loaded')


@router.get('/storefront/settings')
async def storefront_settings(response: Response):
    data = storefront_svc.get_storefront_settings()
    response.headers['Cache-Control'] = 'public, max-age=30, must-revalidate'
    return success_response(data=data, message='Storefront settings retrieved')


@router.get('/media')
async def list_media(response: Response, placement: Optional[str] = None):
    data = storefront_svc.list_media(placement=placement)
    if placement == 'storefront_logo':
        response.headers['Cache-Control'] = 'public, max-age=600, must-revalidate'
    else:
        response.headers['Cache-Control'] = 'public, max-age=300, must-revalidate'
    return success_response(data=data, message='Media retrieved successfully')


@router.get('/media/files/{filename}')
async def serve_media_file(filename: str, response: Response):
    path = media_svc.resolve_file_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail='File not found')
    response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    return FileResponse(str(path), media_type=media_svc.media_content_type(filename))
