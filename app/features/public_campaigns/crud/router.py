"""Public campaign CRUD endpoints: catalog, read (by id or slug), create, update, publish/unpublish/archive."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.constants import PublicCampaignStatus
from app.core.pagination import Page
from app.features.auth.dependencies import GmUserDep, OptionalUserDep
from app.features.public_campaigns.dependencies import PublicCampaignCrudDep
from app.features.public_campaigns.schemas import (
    MAX_LINKS,
    PublicCampaignCreate,
    PublicCampaignListItem,
    PublicCampaignResponse,
    PublicCampaignUpdate,
)

router = APIRouter()

_NOT_FOUND = {404: {"description": "No such public campaign (or it isn't published)."}}
_AUTHOR_ONLY = {
    403: {"description": "Only the author (or the founder) can change it."},
    404: {"description": "No such public campaign."},
}


@router.get("", response_model=Page[PublicCampaignListItem], summary="List public campaigns")
async def list_public_campaigns(
    service: PublicCampaignCrudDep,
    user: OptionalUserDep,
    q: str | None = Query(None, min_length=2, max_length=200, description="Part of the title or pitch."),
    tag_id: Annotated[list[int] | None, Query(max_length=MAX_LINKS, description="Any of these tags.")] = None,
    author_id: int | None = Query(None, description="Only this author's presets."),
    status_filter: Annotated[
        list[PublicCampaignStatus] | None,
        Query(alias="status", description="GM only (others always get `published`). Default: `published`."),
    ] = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """The catalog, newest first, with how many game campaigns each was used for. Open endpoint."""

    return await service.list_catalog(
        user,
        statuses=tuple(status_filter or ()),
        query=q,
        tag_ids=tuple(tag_id or ()),
        author_id=author_id,
        page=page,
        size=size,
    )


@router.get(
    "/{public_campaign_id:int}", response_model=PublicCampaignResponse, summary="Get a public campaign",
    responses=_NOT_FOUND,
)
async def get_public_campaign(public_campaign_id: int, service: PublicCampaignCrudDep, user: OptionalUserDep):
    """
    One public campaign. Players and guests get the description without `:::gm` blocks and `articles: null`;
    GMs also get the article links. Open endpoint.
    """

    return await service.get(public_campaign_id, user)


@router.get(
    "/by-slug/{slug}", response_model=PublicCampaignResponse, summary="Get a public campaign by slug",
    responses=_NOT_FOUND,
)
async def get_public_campaign_by_slug(slug: str, service: PublicCampaignCrudDep, user: OptionalUserDep):
    """Same as `GET /public-campaigns/{id}`, addressed by slug (stable across renames). Open endpoint."""

    return await service.get_by_slug(slug, user)


@router.post(
    "",
    response_model=PublicCampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a public campaign",
    responses={400: {"description": "Unknown tag ids."}, 403: {"description": "The caller is not a GM."}},
)
async def create_public_campaign(data: PublicCampaignCreate, service: PublicCampaignCrudDep, user: GmUserDep):
    """Create a draft: pitch, description (`:::gm` blocks are for GMs only) and tags. **GM only.**"""

    return await service.create(data, user)


@router.patch(
    "/{public_campaign_id:int}",
    response_model=PublicCampaignResponse,
    summary="Update a public campaign",
    responses={**_AUTHOR_ONLY, 400: {"description": "Unknown tag ids."}},
)
async def update_public_campaign(
    public_campaign_id: int, data: PublicCampaignUpdate, service: PublicCampaignCrudDep, user: GmUserDep
):
    """Change title, pitch, description or tags (the slug stays). **Author or founder.**"""

    return await service.update(public_campaign_id, data, user)


@router.post(
    "/{public_campaign_id:int}/publish",
    response_model=PublicCampaignResponse,
    summary="Publish a public campaign",
    responses={**_AUTHOR_ONLY, 409: {"description": "Already published."}},
)
async def publish_public_campaign(public_campaign_id: int, service: PublicCampaignCrudDep, user: GmUserDep):
    """Show it in the catalog, to everyone (draft or archived → published). **Author or founder.**"""

    return await service.transition(public_campaign_id, "publish", user)


@router.post(
    "/{public_campaign_id:int}/unpublish",
    response_model=PublicCampaignResponse,
    summary="Unpublish a public campaign",
    responses={**_AUTHOR_ONLY, 409: {"description": "Not published."}},
)
async def unpublish_public_campaign(public_campaign_id: int, service: PublicCampaignCrudDep, user: GmUserDep):
    """Back to draft. Game campaigns made from it keep their link. **Author or founder.**"""

    return await service.transition(public_campaign_id, "unpublish", user)


@router.post(
    "/{public_campaign_id:int}/archive",
    response_model=PublicCampaignResponse,
    summary="Archive a public campaign",
    responses={**_AUTHOR_ONLY, 409: {"description": "Already archived."}},
)
async def archive_public_campaign(public_campaign_id: int, service: PublicCampaignCrudDep, user: GmUserDep):
    """Take it out of the catalog (moderation included). **Author or founder.**"""

    return await service.transition(public_campaign_id, "archive", user)
