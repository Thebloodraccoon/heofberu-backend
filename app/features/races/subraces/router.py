"""
Assembled ``/races/{race_id}/subraces`` router.

Sub-routers declare no prefix of their own; the prefix is applied here,
and the whole subdomain is mounted onto the ``/races`` router by
``app.features.races.router`` — combined, a path here like
``"/{subrace_id}/features"`` resolves to
``/races/{race_id}/subraces/{subrace_id}/features``.
"""

from fastapi import APIRouter

from app.features.races.subraces.ability_bonuses.router import router as ability_bonuses_router
from app.features.races.subraces.crud.router import router as crud_router
from app.features.races.subraces.features.router import router as features_router

router = APIRouter()

router.include_router(crud_router, prefix="/{race_id}/subraces", tags=["Subraces"])
router.include_router(ability_bonuses_router, prefix="/{race_id}/subraces", tags=["Subraces"])
router.include_router(features_router, prefix="/{race_id}/subraces", tags=["Subraces"])
