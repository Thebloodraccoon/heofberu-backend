"""Assembled ``/tags`` router."""

from fastapi import APIRouter

from app.features.tags.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/tags", tags=["Tags"])
