"""SEO routes — sitemap for search engines."""
from __future__ import annotations

from fastapi import APIRouter, Response

from storefront_backend.services import seo as seo_svc

router = APIRouter(prefix='/seo', tags=['SEO'])


@router.api_route('/sitemap.xml', methods=['GET', 'HEAD'])
async def sitemap_xml():
    xml = seo_svc.build_sitemap_xml()
    return Response(
        content=xml,
        media_type='application/xml',
        headers={
            'Cache-Control': 'public, max-age=3600',
            'Vary': 'Accept-Encoding',
        },
    )
