"""Campaign session endpoints: schedule, list/archive, read, and the GM's create/update/attendance/publish/delete."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, status

from app.constants import CampaignSessionStatus
from app.core.pagination import Page
from app.features.auth.dependencies import CurrentUserDep
from app.features.campaigns.dependencies import CampaignSessionsDep
from app.features.campaigns.sessions.schemas import (
    CampaignSessionBrief,
    CampaignSessionCreate,
    CampaignSessionResponse,
    CampaignSessionUpdate,
    ScheduleEntry,
    SessionAttendanceUpdate,
)

router = APIRouter()

_NOT_FOUND = {404: {"description": "No such campaign/session, or you may not see it."}}
_GM_ONLY = {**_NOT_FOUND, 403: {"description": "Only the campaign's GM (or the founder) can do this."}}
_SESSION = "/{campaign_id:int}/sessions/{session_id:int}"


@router.get("/schedule", response_model=Page[ScheduleEntry], summary="My session schedule")
async def get_schedule(
    service: CampaignSessionsDep,
    current_user: CurrentUserDep,
    starts_from: datetime | None = Query(
        None, alias="from", description="Sessions scheduled at or after this moment. Default: now."
    ),
    until: datetime | None = Query(None, description="Sessions scheduled before this moment. Default: no limit."),
    role: Literal["gm", "player"] | None = Query(
        None, description="`gm` = tables I run, `player` = tables my characters play at. Omit for both."
    ),
    include_cancelled: bool = Query(False, description="Also list cancelled sessions."),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """
    Dated sessions of every campaign you run or play in (archived campaigns left out), soonest first; `viewer_role`
    says whether you are the GM or a player there. Sessions without `scheduled_at` aren't listed.
    """

    return await service.schedule(
        current_user,
        role=role,
        starts_from=starts_from,
        until=until,
        include_cancelled=include_cancelled,
        page=page,
        size=size,
    )


@router.get(
    "/{campaign_id:int}/sessions",
    response_model=Page[CampaignSessionBrief],
    summary="List a campaign's sessions",
    responses=_NOT_FOUND,
)
async def list_sessions(
    campaign_id: int,
    service: CampaignSessionsDep,
    current_user: CurrentUserDep,
    session_status: CampaignSessionStatus | None = Query(
        None, alias="status", description="Only sessions in this status (`played`: the archive)."
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """
    Sessions by number with their date and attendance; players see all of them (the table's schedule and
    archive), the chronicle itself only once published.
    """

    return await service.list_sessions(campaign_id, current_user, status=session_status, page=page, size=size)


@router.get(_SESSION, response_model=CampaignSessionResponse, summary="Get a session", responses=_NOT_FOUND)
async def get_session(campaign_id: int, session_id: int, service: CampaignSessionsDep, current_user: CurrentUserDep):
    """One session with its attendance and chronicle; players get the chronicle once published, without `:::gm`."""

    return await service.get_session(campaign_id, session_id, current_user)


@router.post(
    "/{campaign_id:int}/sessions",
    response_model=CampaignSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a session",
    responses={**_GM_ONLY, 409: {"description": "A session with this number already exists."}},
)
async def create_session(
    campaign_id: int, data: CampaignSessionCreate, service: CampaignSessionsDep, current_user: CurrentUserDep
):
    """
    Add a session; set `scheduled_at` and it shows up in the players' schedule. The chronicle stays unpublished
    (players see the session, not the text) until you publish it; hide your own notes in `:::gm` ... `:::` blocks.
    **Campaign GM only.**
    """

    return await service.create(campaign_id, data, current_user)


@router.patch(
    _SESSION,
    response_model=CampaignSessionResponse,
    summary="Update a session",
    responses={**_GM_ONLY, 409: {"description": "A session with this number already exists."}},
)
async def update_session(
    campaign_id: int,
    session_id: int,
    data: CampaignSessionUpdate,
    service: CampaignSessionsDep,
    current_user: CurrentUserDep,
):
    """Change number, title, status, date or chronicle. **Campaign GM only.**"""

    return await service.update(campaign_id, session_id, data, current_user)


@router.put(
    _SESSION + "/attendance",
    response_model=CampaignSessionResponse,
    summary="Set who attended a session",
    responses={**_GM_ONLY, 400: {"description": "An id isn't a participation of this campaign."}},
)
async def set_session_attendance(
    campaign_id: int,
    session_id: int,
    data: SessionAttendanceUpdate,
    service: CampaignSessionsDep,
    current_user: CurrentUserDep,
):
    """
    Replace the attendance with `participation_ids` (roster ids from `GET /campaigns/{id}/characters`; `[]`
    clears it). Ended participations count too. **Campaign GM only.**
    """

    return await service.set_attendance(campaign_id, session_id, data, current_user)


@router.post(
    _SESSION + "/publish", response_model=CampaignSessionResponse, summary="Publish a session", responses=_GM_ONLY
)
async def publish_session(
    campaign_id: int, session_id: int, service: CampaignSessionsDep, current_user: CurrentUserDep
):
    """Open the chronicle to the players. **Campaign GM only.**"""

    return await service.set_published(campaign_id, session_id, True, current_user)


@router.post(
    _SESSION + "/unpublish", response_model=CampaignSessionResponse, summary="Unpublish a session", responses=_GM_ONLY
)
async def unpublish_session(
    campaign_id: int, session_id: int, service: CampaignSessionsDep, current_user: CurrentUserDep
):
    """Hide the chronicle from the players again (the session itself stays listed). **Campaign GM only.**"""

    return await service.set_published(campaign_id, session_id, False, current_user)


@router.delete(_SESSION, status_code=status.HTTP_204_NO_CONTENT, summary="Delete a session", responses=_GM_ONLY)
async def delete_session(campaign_id: int, session_id: int, service: CampaignSessionsDep, current_user: CurrentUserDep):
    """Delete the session with its attendance and reviews. **Campaign GM only.**"""

    await service.delete(campaign_id, session_id, current_user)
