"""
Assembled ``/items`` router.

The CRUD sub-router declares no prefix of its own; the ``/items`` prefix
is applied here via ``include_router(..., prefix=...)`` so empty-path
routes (``GET ""`` etc.) resolve to ``/items``. The mounted surface
exposes the exact same paths as the previous monolithic endpoints package.
"""

from fastapi import APIRouter

from app.features.items.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/items", tags=["Items"])
