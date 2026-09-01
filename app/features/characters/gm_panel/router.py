"""Assembled /characters/gm-panel router — GM-only writes; player reads in character CRUD."""

from fastapi import APIRouter

from app.features.characters.gm_panel.asi.router import router as asi_router
from app.features.characters.gm_panel.feats.router import router as feats_router
from app.features.characters.gm_panel.features.router import router as features_router
from app.features.characters.gm_panel.hp.router import router as hp_router
from app.features.characters.gm_panel.items.router import router as items_router
from app.features.characters.gm_panel.level.router import router as level_router
from app.features.characters.gm_panel.skills.router import router as skills_router

router = APIRouter()

router.include_router(feats_router, prefix="/{character_id:int}/gm-panel")
router.include_router(features_router, prefix="/{character_id:int}/gm-panel")
router.include_router(items_router, prefix="/{character_id:int}/gm-panel")
router.include_router(asi_router, prefix="/{character_id:int}/gm-panel")
router.include_router(hp_router, prefix="/{character_id:int}/gm-panel")
router.include_router(level_router, prefix="/{character_id:int}/gm-panel")
router.include_router(skills_router, prefix="/{character_id:int}/gm-panel")
