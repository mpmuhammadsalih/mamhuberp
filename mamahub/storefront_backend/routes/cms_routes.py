"""CMS routes."""

from __future__ import annotations



from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field



from storefront_backend.services import cms as cms_svc

from storefront_backend.utils.response import success_response



router = APIRouter(prefix='/cms', tags=['CMS'])





class ContactInquiryBody(BaseModel):

    name: str = Field(min_length=1, max_length=200)

    email: str = Field(min_length=3, max_length=200)

    subject: str = Field(default='General inquiry', max_length=200)

    message: str = Field(min_length=1, max_length=4000)





@router.get('/pages')

async def list_cms_pages():

    data = cms_svc.list_pages()

    return success_response(data=data, message='CMS pages retrieved')





@router.get('/pages/{slug}')

async def get_cms_page(slug: str):

    data = cms_svc.get_page(slug)

    if not data:

        raise HTTPException(status_code=404, detail='Page not found')

    return success_response(data=data, message='CMS page retrieved')





@router.post('/contact')

async def submit_contact_inquiry(body: ContactInquiryBody):

    ok, message = cms_svc.submit_contact(body.model_dump())

    if not ok:

        raise HTTPException(status_code=400, detail=message)

    return success_response(data={'submitted': True}, message=message)

