"""Public campaign showcase endpoints: characters that played it and the players' reviews (open)."""

from fastapi import APIRouter, Query

from app.core.pagination import Page
from app.features.auth.dependencies import OptionalUserDep
from app.features.characters.visibility.schemas import PublicCharacterConcept
from app.features.public_campaigns.dependencies import PublicCampaignShowcaseDep
from app.features.public_campaigns.schemas import PublicCampaignReview

router = APIRouter()

_NOT_FOUND = {404: {"description": "No such public campaign (or it isn't published)."}}


@router.get(
    "/{public_campaign_id:int}/characters",
    response_model=Page[PublicCharacterConcept],
    summary="Characters that played a public campaign",
    responses=_NOT_FOUND,
)
async def list_showcase_characters(
    public_campaign_id: int,
    service: PublicCampaignShowcaseDep,
    user: OptionalUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """
    Archetypes from every game campaign made from this preset, if their owners show them publicly. Concept cards;
    `public_visibility: full` ones have a full card at `GET /characters/{id}/public`. Open endpoint.
    """

    return await service.list_characters(public_campaign_id, user, page=page, size=size)


@router.get(
    "/{public_campaign_id:int}/reviews",
    response_model=Page[PublicCampaignReview],
    summary="Reviews of a public campaign",
    responses=_NOT_FOUND,
)
async def list_showcase_reviews(
    public_campaign_id: int,
    service: PublicCampaignShowcaseDep,
    user: OptionalUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """Players' reviews of the game campaigns made from this preset, newest first. Open endpoint."""

    return await service.list_reviews(public_campaign_id, user, page=page, size=size)
