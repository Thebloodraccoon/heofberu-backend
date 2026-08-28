"""
Assembled ``/characters/gm-panel`` router (query-style resource IDs).

Sub-routers declare no prefix of their own; the static ``/gm-panel``
prefix is applied here, and the whole subdomain is mounted onto the
``/characters`` router by ``app.features.characters.router`` — combined,
a path here like ``"/feats"`` resolves to
``/characters/gm-panel/feats?character_id=...``. The owning character is
identified by the required ``character_id`` query parameter on every
endpoint; per-grant operations additionally take their grant ID as a
query parameter (``feat_id``, ``item_id``, ...).

Every route is a GM-only write via ``GmUserDep``, except the read-only
``/stats``, ``GET /max-level``, ``/asi`` listing and ``/items`` listing
(GM/owner).
The matching player-facing reads live in the plain character CRUD
(``GET /characters/feats?character_id=...``,
``GET /characters/features?character_id=...``).
"""

from fastapi import APIRouter

from app.features.characters.gm_panel.asi.router import router as asi_router
from app.features.characters.gm_panel.feats.router import router as feats_router
from app.features.characters.gm_panel.features.router import router as features_router
from app.features.characters.gm_panel.hp.router import router as hp_router
from app.features.characters.gm_panel.items.router import router as items_router
from app.features.characters.gm_panel.level.router import router as level_router
from app.features.characters.gm_panel.skills.router import router as skills_router
from app.features.characters.gm_panel.stats.router import router as stats_router

router = APIRouter()

router.include_router(feats_router, prefix="/{character_id:int}gm-panel")
router.include_router(features_router, prefix="/{character_id:int}/gm-panel")
router.include_router(items_router, prefix="/{character_id:int}/gm-panel")
router.include_router(asi_router, prefix="/{character_id:int}/gm-panel")
router.include_router(hp_router, prefix="/{character_id:int}/gm-panel")
router.include_router(level_router, prefix="/{character_id:int}/gm-panel")
router.include_router(skills_router, prefix="/{character_id:int}/gm-panel")
router.include_router(stats_router, prefix="/{character_id:int}/gm-panel")
