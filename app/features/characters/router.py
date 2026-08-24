"""Aggregates the character sub-domain routers under /characters."""

from fastapi import APIRouter

from app.features.characters.attacks.router import router as attacks_router
from app.features.characters.conditions.router import router as conditions_router
from app.features.characters.crud.router import router as core_router
from app.features.characters.gm_panel.router import router as gm_panel_router
from app.features.characters.progression.router import router as progression_router
from app.features.characters.spells.router import router as spells_router

router = APIRouter()

router.include_router(core_router, prefix="/characters", tags=["Characters"])
router.include_router(spells_router, prefix="/characters", tags=["Characters Spells"])
router.include_router(attacks_router, prefix="/characters", tags=["Characters Attacks"])
router.include_router(gm_panel_router, prefix="/characters", tags=["Characters GM Panel"])
router.include_router(conditions_router, prefix="/characters", tags=["Characters Conditions"])
router.include_router(progression_router, prefix="/characters", tags=["Characters Progression"])
