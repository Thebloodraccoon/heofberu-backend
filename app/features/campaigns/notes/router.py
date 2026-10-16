"""The GM's private campaign notes endpoints (all GM-only)."""

from fastapi import APIRouter, Query, status

from app.core.pagination import Page
from app.features.auth.dependencies import CurrentUserDep
from app.features.campaigns.dependencies import CampaignNotesDep
from app.features.campaigns.notes.schemas import CampaignNoteCreate, CampaignNoteResponse, CampaignNoteUpdate

router = APIRouter()

_GM_ONLY = {
    403: {"description": "Only the campaign's GM (or the founder) can see notes."},
    404: {"description": "No such campaign/note, or you are not part of the campaign."},
}
_NOTE = "/{campaign_id:int}/notes/{note_id:int}"


@router.get(
    "/{campaign_id:int}/notes", response_model=Page[CampaignNoteResponse], summary="List notes", responses=_GM_ONLY
)
async def list_notes(
    campaign_id: int,
    service: CampaignNotesDep,
    current_user: CurrentUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """The GM's private notes, most recently updated first. **Campaign GM only.**"""

    return await service.list_notes(campaign_id, current_user, page=page, size=size)


@router.get(_NOTE, response_model=CampaignNoteResponse, summary="Get a note", responses=_GM_ONLY)
async def get_note(campaign_id: int, note_id: int, service: CampaignNotesDep, current_user: CurrentUserDep):
    """One note. **Campaign GM only.**"""

    return await service.get_note(campaign_id, note_id, current_user)


@router.post(
    "/{campaign_id:int}/notes",
    response_model=CampaignNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note",
    responses=_GM_ONLY,
)
async def create_note(
    campaign_id: int, data: CampaignNoteCreate, service: CampaignNotesDep, current_user: CurrentUserDep
):
    """Add a private note (plot lines, NPCs, prep). **Campaign GM only.**"""

    return await service.create(campaign_id, data, current_user)


@router.patch(_NOTE, response_model=CampaignNoteResponse, summary="Update a note", responses=_GM_ONLY)
async def update_note(
    campaign_id: int, note_id: int, data: CampaignNoteUpdate, service: CampaignNotesDep, current_user: CurrentUserDep
):
    """Change a note. **Campaign GM only.**"""

    return await service.update(campaign_id, note_id, data, current_user)


@router.delete(_NOTE, status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note", responses=_GM_ONLY)
async def delete_note(campaign_id: int, note_id: int, service: CampaignNotesDep, current_user: CurrentUserDep):
    """Delete a note. **Campaign GM only.**"""

    await service.delete(campaign_id, note_id, current_user)
