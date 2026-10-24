"""Assembled ``/public-campaigns`` router: one ``include_router`` per capability (see ``README.md`` for the map)."""

from fastapi import APIRouter

from app.features.public_campaigns.articles.router import router as articles_router
from app.features.public_campaigns.crud.router import router as crud_router
from app.features.public_campaigns.showcase.router import router as showcase_router

router = APIRouter()

router.include_router(crud_router, prefix="/public-campaigns", tags=["Public Campaigns"])
router.include_router(articles_router, prefix="/public-campaigns", tags=["Public Campaigns"])
router.include_router(showcase_router, prefix="/public-campaigns", tags=["Public Campaigns Showcase"])
