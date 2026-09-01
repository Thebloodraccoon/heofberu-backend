"""Assembled ``/races`` router."""

from fastapi import APIRouter

from app.features.races.ability_bonuses.router import router as ability_bonuses_router
from app.features.races.crud.router import router as crud_router
from app.features.races.features.router import router as features_router
from app.features.races.image.router import router as image_router
from app.features.races.skills.router import router as skills_router

router = APIRouter()

router.include_router(crud_router, prefix="/races", tags=["Races"])
router.include_router(ability_bonuses_router, prefix="/races", tags=["Races"])
router.include_router(skills_router, prefix="/races", tags=["Races"])
router.include_router(features_router, prefix="/races", tags=["Races"])
router.include_router(image_router, prefix="/races", tags=["Races Images"])
