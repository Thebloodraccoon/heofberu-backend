"""Assembled ``/classes/subclasses`` router (query-style parent ID)."""

from fastapi import APIRouter

from app.features.subclasses.crud.router import router as crud_router
from app.features.subclasses.features.router import router as features_router
from app.features.subclasses.image.router import router as image_router

router = APIRouter()

router.include_router(crud_router, prefix="/subclasses", tags=["Subclasses"])
router.include_router(features_router, prefix="/subclasses", tags=["Subclasses"])
router.include_router(image_router, prefix="/subclasses", tags=["Subclasses Images"])
