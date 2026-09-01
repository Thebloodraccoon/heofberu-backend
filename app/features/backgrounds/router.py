"""Assembled ``/backgrounds`` router."""

from fastapi import APIRouter

from app.features.backgrounds.crud.router import router as crud_router
from app.features.backgrounds.features.router import router as features_router
from app.features.backgrounds.items.router import router as items_router
from app.features.backgrounds.skills.router import router as skills_router

router = APIRouter()

router.include_router(crud_router, prefix="/backgrounds", tags=["Backgrounds"])
router.include_router(skills_router, prefix="/backgrounds/{background_id}", tags=["Backgrounds"])
router.include_router(items_router, prefix="/backgrounds/{background_id}", tags=["Backgrounds"])
router.include_router(features_router, prefix="/backgrounds/{background_id}", tags=["Backgrounds"])
