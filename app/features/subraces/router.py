"""Assembled ``/races/subraces`` router (query-style parent ID)."""

from fastapi import APIRouter

from app.features.subraces.ability_bonuses.router import router as ability_bonuses_router
from app.features.subraces.crud.router import router as crud_router
from app.features.subraces.features.router import router as features_router
from app.features.subraces.image.router import router as image_router

router = APIRouter()

router.include_router(crud_router, prefix="/subraces", tags=["Subraces"])
router.include_router(ability_bonuses_router, prefix="/subraces", tags=["Subraces"])
router.include_router(features_router, prefix="/subraces", tags=["Subraces"])
router.include_router(image_router, prefix="/subraces", tags=["Subraces Images"])
