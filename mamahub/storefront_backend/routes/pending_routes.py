"""Legacy placeholder routes for endpoints not yet ported."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=['Pending'])


def _pending(feature: str):
    raise HTTPException(
        status_code=501,
        detail=f'{feature} is not yet available on Nova storefront API.',
    )
