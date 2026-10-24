"""Campaign roster endpoints: list, candidate search, add, status change."""

from fastapi import APIRouter, Query, status

from app.core.pagination import Page
from app.features.auth.dependencies import CurrentUserDep
from app.features.campaigns.characters.schemas import (
    CampaignCharacterAdd,
    CampaignCharacterResponse,
    CampaignCharacterStatusUpdate,
    CharacterCandidate,
)
from app.features.campaigns.dependencies import CampaignCharactersDep

router = APIRouter()

_NOT_FOUND = {404: {"description": "No such campaign, or you are neither its GM nor one of its players."}}
_GM_ONLY = {**_NOT_FOUND, 403: {"description": "Only the campaign's GM (or the founder) can do this."}}


@router.get(
    "/{campaign_id:int}/characters",
    response_model=Page[CampaignCharacterResponse],
    summary="List a campaign's characters",
    responses=_NOT_FOUND,
)
async def list_campaign_characters(
    campaign_id: int,
    service: CampaignCharactersDep,
    current_user: CurrentUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """The roster by join time. The GM also sees removed characters (history); players don't."""

    return await service.list_roster(campaign_id, current_user, page=page, size=size)


@router.get(
    "/{campaign_id:int}/characters/candidates",
    response_model=Page[CharacterCandidate],
    summary="Search free characters to add",
    responses=_GM_ONLY,
)
async def search_candidates(
    campaign_id: int,
    service: CampaignCharactersDep,
    current_user: CurrentUserDep,
    player: str | None = Query(None, max_length=100, description="Part of the player's username."),
    q: str | None = Query(None, max_length=200, description="Part of the character's name."),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """
    Characters that play in no campaign right now, by player and/or character name. Shows only the brief card
    (name, class, race, level, player), never the sheet or backstory. **Campaign GM only.**
    """

    return await service.search_candidates(campaign_id, current_user, player=player, query=q, page=page, size=size)


@router.post(
    "/{campaign_id:int}/characters",
    response_model=CampaignCharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a character to a campaign",
    responses={
        **_GM_ONLY,
        409: {"description": "The character already plays in a campaign, or this campaign is closed/archived."},
    },
)
async def add_campaign_character(
    campaign_id: int, data: CampaignCharacterAdd, service: CampaignCharactersDep, current_user: CurrentUserDep
):
    """
    Add a free character. The player isn't asked and can't leave; the campaign shows up in their "my campaigns"
    and the GM gets access to the character's sheet while it is active here. **Campaign GM only.**
    """

    return await service.add(campaign_id, data, current_user)


@router.patch(
    "/{campaign_id:int}/characters/{participation_id:int}",
    response_model=CampaignCharacterResponse,
    summary="Change a character's status in a campaign",
    responses={**_GM_ONLY, 409: {"description": "That status change isn't allowed."}},
)
async def set_campaign_character_status(
    campaign_id: int,
    participation_id: int,
    data: CampaignCharacterStatusUpdate,
    service: CampaignCharactersDep,
    current_user: CurrentUserDep,
):
    """
    `active` → `dead`/`retired`/`removed`, or anything → `removed`. Any of them frees the character; `removed` also
    takes away the player's access to the campaign. **Campaign GM only.**
    """

    return await service.set_status(campaign_id, participation_id, data, current_user)
