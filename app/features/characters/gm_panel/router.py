"""
Assembled ``/characters/{character_id}/gm-panel`` router.

Sub-routers declare no prefix of their own; the prefix is applied here,
and the whole subdomain is mounted onto the ``/characters`` router by
``app.features.characters.router`` — combined, a path here like
``"/feats"`` resolves to ``/characters/{character_id}/gm-panel/feats``.

Every route is a GM-only write via ``GmUserDep``, except the read-only
``/stats``, ``/asi`` listing and ``/items`` listing (GM/owner).
The matching player-facing reads live in the plain character CRUD
(``GET /characters/{id}/feats``, ``GET /characters/{id}/features``).
"""

from fastapi import APIRouter

from app.features.characters.gm_panel.asi.router import router as asi_router
from app.features.characters.gm_panel.feats.router import router as feats_router
from app.features.characters.gm_panel.features.router import router as features_router
from app.features.characters.gm_panel.hp.router import router as hp_router
from app.features.characters.gm_panel.items.router import router as items_router
from app.features.characters.gm_panel.skills.router import router as skills_router
from app.features.characters.gm_panel.stats.router import router as stats_router

router = APIRouter()

router.include_router(feats_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel Feats"])
router.include_router(features_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel Features"])
router.include_router(items_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel Items"])
router.include_router(asi_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel ASI"])
router.include_router(hp_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel HP"])
router.include_router(skills_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel Skills"])
router.include_router(stats_router, prefix="/{character_id}/gm-panel", tags=["Character GM Panel STATS"])
