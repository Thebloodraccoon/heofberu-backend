"""
Assembled ``/features`` router.

The CRUD sub-router declares no prefix of its own; the ``/features``
prefix is applied here via ``include_router(..., prefix=...)`` so
empty-path routes (``GET ""`` etc.) resolve to ``/features``. The mounted
surface exposes the exact same paths as the previous monolithic endpoints
package.
"""

from fastapi import APIRouter

from app.features.features.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/features", tags=["Features"])
