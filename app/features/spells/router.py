"""Assembled ``/spells`` router."""

from fastapi import APIRouter

from app.features.spells.availability.router import router as availability_router
from app.features.spells.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/spells", tags=["Spells"])
router.include_router(availability_router, prefix="/spells", tags=["Spells"])
