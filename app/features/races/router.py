"""
Assembled ``/races`` router.

Each capability sub-router declares no prefix of its own; the ``/races``
prefix is applied here via ``include_router(..., prefix=...)`` so
empty-path routes (``GET ""`` etc.) resolve to ``/races``. The subraces
subdomain mounts under the same prefix: ``/races/subraces/...`` with the
owning race passed as the required ``race_id`` query parameter.
The mounted surface exposes the exact same paths as the previous
monolithic endpoints package.
"""

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
