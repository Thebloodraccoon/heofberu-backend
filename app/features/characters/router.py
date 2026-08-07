"""Aggregates the character sub-domain routers under /characters."""

from fastapi import APIRouter

from app.features.characters.attacks.endpoints import router as attacks_router
from app.features.characters.conditions.endpoints import router as conditions_router
from app.features.characters.core.endpoints import router as core_router
from app.features.characters.feats.endpoints import router as feats_router
from app.features.characters.features.endpoints import router as features_router
from app.features.characters.items.endpoints import router as items_router
from app.features.characters.proficiencies.endpoints import router as proficiencies_router
from app.features.characters.progression.endpoints import router as progression_router
from app.features.characters.spells.endpoints import router as spells_router

router = APIRouter(prefix="/characters")

router.include_router(core_router)
router.include_router(proficiencies_router)
router.include_router(spells_router)
router.include_router(attacks_router)
router.include_router(feats_router)
router.include_router(features_router)
router.include_router(items_router)
router.include_router(conditions_router)
router.include_router(progression_router)
