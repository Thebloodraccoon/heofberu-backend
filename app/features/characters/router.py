"""Aggregates the character sub-domain routers under /characters."""

from fastapi import APIRouter

from app.features.characters.attacks.router import router as attacks_router
from app.features.characters.backstory.router import router as backstory_router
from app.features.characters.conditions.router import router as conditions_router
from app.features.characters.crud.router import router as core_router
from app.features.characters.feats.router import router as feats_router
from app.features.characters.features.router import router as features_router
from app.features.characters.gm_panel.router import router as gm_panel_router
from app.features.characters.grants.router import router as grants_router
from app.features.characters.items.router import router as items_router
from app.features.characters.proficiencies.router import router as proficiencies_router
from app.features.characters.progression.router import router as progression_router
from app.features.characters.spells.router import router as spells_router

router = APIRouter()

router.include_router(core_router, prefix="/characters", tags=["Characters"])
router.include_router(items_router, prefix="/characters", tags=["Characters Items"])
router.include_router(feats_router, prefix="/characters", tags=["Characters Feats"])
router.include_router(features_router, prefix="/characters", tags=["Characters Features"])
router.include_router(conditions_router, prefix="/characters", tags=["Characters Conditions"])
router.include_router(proficiencies_router, prefix="/characters", tags=["Characters Proficiencies"])
router.include_router(attacks_router, prefix="/characters", tags=["Characters Attacks"])
router.include_router(spells_router, prefix="/characters", tags=["Characters Spells"])
router.include_router(backstory_router, prefix="/characters", tags=["Characters Backstory"])
router.include_router(progression_router, prefix="/characters", tags=["Characters Progression"])
router.include_router(gm_panel_router, prefix="/characters", tags=["Characters GM Panel"])
router.include_router(grants_router, prefix="/characters", tags=["Characters Feature Grants"])

