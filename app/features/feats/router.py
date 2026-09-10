"""Assembled ``/feats`` router."""

from fastapi import APIRouter

from app.features.feats.crud.router import router as crud_router
from app.features.features.effects.router import router as effects_router

router = APIRouter()

router.include_router(crud_router, prefix="/feats", tags=["Feats"])

# A feat IS a Feature (source_type=FEAT) — reuse the feature engine's effect
# endpoints verbatim rather than reimplementing skill/save/armor/weapon/spell
# effect CRUD for feats. FeatureEffectsService is source_type-agnostic, so
# mounting the same router under /feats just gives feats a discoverable
# write surface for effects beyond the ASI choice (e.g. Skilled's 3 skill
# picks, Magic Initiate's granted spells) at their own path.
router.include_router(effects_router, prefix="/feats", tags=["Feats"])
