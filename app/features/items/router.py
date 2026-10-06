"""Assembled ``/items`` router."""

from fastapi import APIRouter

from app.features.items.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/items", tags=["Items"])
