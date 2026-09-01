"""Assembled ``/feats`` router."""

from fastapi import APIRouter

from app.features.feats.asi.router import router as asi_router
from app.features.feats.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/feats", tags=["Feats"])
router.include_router(asi_router, prefix="/feats", tags=["Feats"])
