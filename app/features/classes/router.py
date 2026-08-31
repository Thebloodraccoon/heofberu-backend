"""
Assembled ``/classes`` router.

Subclasses are now a standalone module mounted separately — not nested
under ``/classes/{class_id}``.
"""

from fastapi import APIRouter

from app.features.classes.armor.router import router as armor_router
from app.features.classes.crud.router import router as crud_router
from app.features.classes.features.router import router as features_router
from app.features.classes.image.router import router as image_router
from app.features.classes.items.router import router as items_router
from app.features.classes.progression.router import router as progression_router
from app.features.classes.skills.router import router as skills_router
from app.features.subclasses.router import router as subclasses_router
from app.features.classes.throws.router import router as throws_router
from app.features.classes.weapons.router import router as weapons_router

router = APIRouter()

router.include_router(crud_router, prefix="/classes", tags=["Classes"])
router.include_router(skills_router, prefix="/classes", tags=["Classes"])
router.include_router(features_router, prefix="/classes", tags=["Classes"])
router.include_router(items_router, prefix="/classes", tags=["Classes"])
router.include_router(throws_router, prefix="/classes", tags=["Classes"])
router.include_router(progression_router, prefix="/classes", tags=["Classes"])
router.include_router(armor_router, prefix="/classes", tags=["Classes"])
router.include_router(weapons_router, prefix="/classes", tags=["Classes"])
router.include_router(image_router, prefix="/classes", tags=["Classes Images"])
