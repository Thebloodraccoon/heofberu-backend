"""Campaign CRUD endpoints: create, "my campaigns", read, update, archive/restore."""

from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.pagination import Page
from app.features.auth.dependencies import CurrentUserDep, GmUserDep
from app.features.campaigns.crud.schemas import CampaignCreate, CampaignListItem, CampaignResponse, CampaignUpdate
from app.features.campaigns.dependencies import CampaignCrudDep

router = APIRouter()

_NOT_FOUND = {404: {"description": "No such campaign, or you are neither its GM nor one of its players."}}
_GM_ONLY = {**_NOT_FOUND, 403: {"description": "Only the campaign's GM (or the founder) can do this."}}


@router.post(
    "",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign",
    responses={
        400: {"description": "`public_campaign_id` doesn't exist or isn't published."},
        403: {"description": "The caller is not a GM."},
    },
)
async def create_campaign(data: CampaignCreate, service: CampaignCrudDep, current_user: GmUserDep):
    """
    Create a game campaign owned by the caller. With `public_campaign_id` it is made from that public campaign
    (preset): omitted `title`/`description_markdown` are copied, and the campaign shows up in the preset's
    showcase and reviews. **GM only.**
    """

    return await service.create(data, current_user)


@router.get("", response_model=Page[CampaignListItem], summary="List my campaigns")
async def list_campaigns(
    service: CampaignCrudDep,
    current_user: CurrentUserDep,
    role: Literal["gm", "player"] | None = Query(
        None, description="`gm` = campaigns I run, `player` = campaigns my characters play in. Omit for both."
    ),
    q: str | None = Query(None, max_length=200, description="Part of the campaign title (case-insensitive)."),
    include_archived: bool = Query(False, description="Also list archived campaigns."),
    all_campaigns: bool = Query(
        False, description="Founder only (ignored otherwise): every campaign. Can't be combined with `role` (400)."
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """Campaigns the caller runs or plays in, most recently updated first."""

    return await service.list_mine(
        current_user,
        role=role,
        query=q,
        include_archived=include_archived,
        all_campaigns=all_campaigns,
        page=page,
        size=size,
    )


@router.get("/{campaign_id:int}", response_model=CampaignResponse, summary="Get a campaign", responses=_NOT_FOUND)
async def get_campaign(campaign_id: int, service: CampaignCrudDep, current_user: CurrentUserDep):
    """The campaign; players get the description without `:::gm` blocks (`viewer_role` says which view it is)."""

    return await service.get(campaign_id, current_user)


@router.patch(
    "/{campaign_id:int}",
    response_model=CampaignResponse,
    summary="Update a campaign",
    responses={**_GM_ONLY, 400: {"description": "`public_campaign_id` doesn't exist or isn't published."}},
)
async def update_campaign(
    campaign_id: int, data: CampaignUpdate, service: CampaignCrudDep, current_user: CurrentUserDep
):
    """
    Change title, description, status or the preset link (`null` unlinks). Setting `finished`/`abandoned` releases
    the active characters (they become free for other campaigns). **Campaign GM only.**
    """

    return await service.update(campaign_id, data, current_user)


@router.post(
    "/{campaign_id:int}/archive", response_model=CampaignResponse, summary="Archive a campaign", responses=_GM_ONLY
)
async def archive_campaign(campaign_id: int, service: CampaignCrudDep, current_user: CurrentUserDep):
    """Archive: hidden from "my campaigns" by default, still readable by its players; characters released."""

    return await service.archive(campaign_id, current_user)


@router.post(
    "/{campaign_id:int}/restore", response_model=CampaignResponse, summary="Restore an archived campaign",
    responses=_GM_ONLY,
)
async def restore_campaign(campaign_id: int, service: CampaignCrudDep, current_user: CurrentUserDep):
    """Take the campaign out of the archive. Released characters must be added again. **Campaign GM only.**"""

    return await service.restore(campaign_id, current_user)
