"""Public campaign article link endpoints (GM-only reads, author/founder writes)."""

from fastapi import APIRouter

from app.features.auth.dependencies import GmUserDep
from app.features.public_campaigns.dependencies import PublicCampaignArticlesDep
from app.features.public_campaigns.schemas import PublicCampaignArticleLink, PublicCampaignArticlesUpdate

router = APIRouter()


@router.get(
    "/{public_campaign_id:int}/articles",
    response_model=list[PublicCampaignArticleLink],
    summary="List a public campaign's articles",
    responses={403: {"description": "The caller is not a GM."}, 404: {"description": "No such public campaign."}},
)
async def list_public_campaign_articles(public_campaign_id: int, service: PublicCampaignArticlesDep, user: GmUserDep):
    """The knowledge-base articles this preset points GMs to, in order. **GM only.**"""

    return await service.list_links(public_campaign_id, user)


@router.put(
    "/{public_campaign_id:int}/articles",
    response_model=list[PublicCampaignArticleLink],
    summary="Replace a public campaign's articles",
    responses={
        400: {"description": "Unknown article ids."},
        403: {"description": "Only the author (or the founder) can change it."},
        404: {"description": "No such public campaign."},
    },
)
async def set_public_campaign_articles(
    public_campaign_id: int, data: PublicCampaignArticlesUpdate, service: PublicCampaignArticlesDep, user: GmUserDep
):
    """Replace all article links (`position` defaults to the list order; `[]` clears them). **Author or founder.**"""

    return await service.set_links(public_campaign_id, data, user)
