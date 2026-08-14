"""
Assembled ``/classes`` router.

Each capability sub-router declares no prefix of its own; the ``/classes``
prefix is applied here via ``include_router(..., prefix=...)`` so
empty-path routes (``GET ""`` etc.) resolve to ``/classes``. The
subclasses subdomain mounts under the same prefix:
``/classes/{class_id}/subclasses/...``. The mounted surface exposes the
exact same paths as the previous monolithic endpoints package.
"""

from fastapi import APIRouter

from app.features.classes.armor.router import router as armor_router
from app.features.classes.crud.router import router as crud_router
from app.features.classes.features.router import router as features_router
from app.features.classes.items.router import router as items_router
from app.features.classes.progression.router import router as progression_router
from app.features.classes.skills.router import router as skills_router
from app.features.classes.subclasses.router import router as subclasses_router
from app.features.classes.throws.router import router as throws_router

router = APIRouter()

router.include_router(crud_router, prefix="/classes", tags=["Classes"])
router.include_router(skills_router, prefix="/classes", tags=["Classes"])
router.include_router(features_router, prefix="/classes", tags=["Classes"])
router.include_router(items_router, prefix="/classes", tags=["Classes"])
router.include_router(throws_router, prefix="/classes", tags=["Classes"])
router.include_router(progression_router, prefix="/classes", tags=["Classes"])
router.include_router(armor_router, prefix="/classes", tags=["Classes"])
router.include_router(subclasses_router, prefix="/classes")
