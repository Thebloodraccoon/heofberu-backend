"""
Assembled ``/backgrounds`` router.

Each capability sub-router declares no prefix of its own; the
``/backgrounds`` prefix is applied here via ``include_router(..., prefix=...)``
so empty-path routes (``GET ""`` etc.) resolve to ``/backgrounds``. The
mounted surface exposes the exact same paths as the previous monolithic
endpoints package.
"""

from fastapi import APIRouter

from app.features.backgrounds.crud.router import router as crud_router
from app.features.backgrounds.features.router import router as features_router
from app.features.backgrounds.items.router import router as items_router
from app.features.backgrounds.skills.router import router as skills_router

router = APIRouter()

router.include_router(crud_router, prefix="/backgrounds", tags=["Backgrounds"])
router.include_router(skills_router, prefix="/backgrounds", tags=["Backgrounds"])
router.include_router(items_router, prefix="/backgrounds", tags=["Backgrounds"])
router.include_router(features_router, prefix="/backgrounds", tags=["Backgrounds"])
