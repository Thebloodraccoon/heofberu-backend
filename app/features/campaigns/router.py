"""Assembled ``/campaigns`` router: one ``include_router`` per capability (see ``README.md`` for the map)."""

from fastapi import APIRouter

from app.features.campaigns.characters.router import router as characters_router
from app.features.campaigns.crud.router import router as crud_router
from app.features.campaigns.notes.router import router as notes_router
from app.features.campaigns.reviews.router import moderation_router as reviews_moderation_router
from app.features.campaigns.reviews.router import router as reviews_router
from app.features.campaigns.reviews.router import session_moderation_router as session_reviews_moderation_router
from app.features.campaigns.sessions.router import router as sessions_router

router = APIRouter()

router.include_router(crud_router, prefix="/campaigns", tags=["Campaigns"])
router.include_router(characters_router, prefix="/campaigns", tags=["Campaigns Characters"])
router.include_router(sessions_router, prefix="/campaigns", tags=["Campaigns Sessions"])
router.include_router(notes_router, prefix="/campaigns", tags=["Campaigns Notes"])
router.include_router(reviews_router, prefix="/campaigns", tags=["Campaigns Reviews"])
router.include_router(reviews_moderation_router, prefix="/campaign-reviews", tags=["Campaigns Reviews"])
router.include_router(session_reviews_moderation_router, prefix="/session-reviews", tags=["Campaigns Reviews"])
