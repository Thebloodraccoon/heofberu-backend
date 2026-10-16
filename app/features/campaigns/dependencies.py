"""Per-capability dependency providers for the game campaigns domain (one ``Campaign*Dep`` per service)."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.campaigns.characters.service import CampaignCharactersService
from app.features.campaigns.crud.service import CampaignCrudService
from app.features.campaigns.notes.service import CampaignNotesService
from app.features.campaigns.reviews.service import CampaignReviewsService
from app.features.campaigns.sessions.service import CampaignSessionsService


def get_campaign_crud_service(db: DatabaseDep) -> CampaignCrudService:
    """The campaign itself."""

    return CampaignCrudService(db)


CampaignCrudDep = Annotated[CampaignCrudService, Depends(get_campaign_crud_service)]


def get_campaign_characters_service(db: DatabaseDep) -> CampaignCharactersService:
    """The roster and the free-character search."""

    return CampaignCharactersService(db)


CampaignCharactersDep = Annotated[CampaignCharactersService, Depends(get_campaign_characters_service)]


def get_campaign_sessions_service(db: DatabaseDep) -> CampaignSessionsService:
    """Sessions and their chronicle."""

    return CampaignSessionsService(db)


CampaignSessionsDep = Annotated[CampaignSessionsService, Depends(get_campaign_sessions_service)]


def get_campaign_notes_service(db: DatabaseDep) -> CampaignNotesService:
    """The GM's private notes."""

    return CampaignNotesService(db)


CampaignNotesDep = Annotated[CampaignNotesService, Depends(get_campaign_notes_service)]


def get_campaign_reviews_service(db: DatabaseDep) -> CampaignReviewsService:
    """Campaign and session reviews."""

    return CampaignReviewsService(db)


CampaignReviewsDep = Annotated[CampaignReviewsService, Depends(get_campaign_reviews_service)]
