"""Assembled ``/items`` router: the core, one capability per kind, the property dictionary, item effects."""

from fastapi import APIRouter

from app.features.items.armor.router import router as armor_router
from app.features.items.crud.router import router as crud_router
from app.features.items.effects.router import router as effects_router
from app.features.items.properties.router import router as properties_router
from app.features.items.tools.router import router as tools_router
from app.features.items.weapons.router import router as weapons_router

router = APIRouter()

router.include_router(crud_router, prefix="/items", tags=["Items"])
router.include_router(weapons_router, prefix="/items", tags=["Items"])
router.include_router(armor_router, prefix="/items", tags=["Items"])
router.include_router(tools_router, prefix="/items", tags=["Items"])
router.include_router(properties_router, prefix="/items", tags=["Items"])
router.include_router(effects_router, prefix="/items", tags=["Items"])
