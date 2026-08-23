"""
Assembled ``/feats`` router.

Each capability sub-router declares no prefix of its own; the ``/feats``
prefix is applied here via ``include_router(..., prefix=...)`` so
empty-path routes (``GET ""`` etc.) resolve to ``/feats``. The mounted
surface exposes the exact same paths as the previous monolithic endpoints
package.
"""

from fastapi import APIRouter

from app.features.feats.asi.router import router as asi_router
from app.features.feats.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/feats", tags=["Feats"])
router.include_router(asi_router, prefix="/feats", tags=["Feats"])
