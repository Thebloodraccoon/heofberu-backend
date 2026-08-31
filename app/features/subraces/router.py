"""
Assembled ``/races/subraces`` router (query-style parent ID).

Sub-routers declare no prefix of their own; the static ``/subraces``
prefix is applied here, and the whole subdomain is mounted onto the
``/races`` router by ``app.features.races.router`` — combined, a path
here like ``"/features"`` resolves to
``/races/subraces/features?race_id=...``. The owning race is identified
by the required ``race_id`` query parameter on every endpoint.
"""

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
