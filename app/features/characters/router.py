from fastapi import APIRouter

from app.features.characters.attacks.endpoints import router as attacks_router
from app.features.characters.core.endpoints import router as core_router
from app.features.characters.feats.endpoints import router as feats_router
from app.features.characters.proficiencies.endpoints import router as proficiencies_router
from app.features.characters.spells.endpoints import router as spells_router

router = APIRouter(prefix="/characters")

router.include_router(core_router)
router.include_router(proficiencies_router)
router.include_router(spells_router)
router.include_router(attacks_router)
router.include_router(feats_router)
