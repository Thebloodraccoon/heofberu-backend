"""Assembled ``/feats`` router."""

from fastapi import APIRouter, Depends

from app.features.feats.crud.router import router as crud_router
from app.features.feats.dependencies import require_feat
from app.features.features.effects.router import router as effects_router

router = APIRouter()

router.include_router(crud_router, prefix="/feats", tags=["Feats"])

# A feat IS a Feature (source_type=FEAT) — reuse the feature engine's effect
# endpoints rather than reimplementing effect CRUD for feats. The engine is
# source_type-agnostic, so ``require_feat`` keeps this mount from reaching
# class/race/background features through a ``/feats`` URL.
router.include_router(effects_router, prefix="/feats", tags=["Feats"], dependencies=[Depends(require_feat)])
