"""Assembled ``/skills`` router."""

from fastapi import APIRouter

from app.features.skills.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/skills", tags=["Skills"])
