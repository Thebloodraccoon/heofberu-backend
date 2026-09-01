"""Assembled ``/features`` router."""

from fastapi import APIRouter

from app.features.features.ability_increases.router import router as ability_increases_router
from app.features.features.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/features", tags=["Features"])
router.include_router(ability_increases_router, prefix="/features", tags=["Features"])
