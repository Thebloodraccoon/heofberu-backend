"""Assembled ``/features`` router."""

from fastapi import APIRouter

from app.features.features.crud.router import router as crud_router
from app.features.features.effects.router import router as effects_router

router = APIRouter()

router.include_router(crud_router, prefix="/features", tags=["Features"])
router.include_router(effects_router, prefix="/features", tags=["Features"])
