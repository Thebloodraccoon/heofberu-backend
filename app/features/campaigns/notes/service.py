"""The GM's private campaign notes: only the campaign's GM and the founder ever see them."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, paginate
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.exceptions import CampaignNoteNotFoundException
from app.features.campaigns.notes.repository import CampaignNotesRepository
from app.features.campaigns.notes.schemas import CampaignNoteCreate, CampaignNoteResponse, CampaignNoteUpdate
from app.features.users.schemas import UserResponse
from app.models.campaigns.campaign_note_model import CampaignNote


class CampaignNotesService(CampaignScopedService):
    """CRUD of the GM's notes; every call is GM-only (players get 403, outsiders 404)."""

    repository: CampaignNotesRepository

    def __init__(self, db: AsyncSession):
        """Initialize the notes repository."""

        super().__init__(CampaignNotesRepository(db))

    async def list_notes(
        self, campaign_id: int, current_user: UserResponse, *, page: int, size: int
    ) -> Page[CampaignNoteResponse]:
        """The campaign's notes, most recently updated first."""

        await self._gm(campaign_id, current_user)
        skip, limit = paginate(page, size)
        notes, total = await self.repository.list_for_campaign(campaign_id, skip=skip, limit=limit)
        return Page(
            items=[CampaignNoteResponse.model_validate(note) for note in notes], total=total, page=page, size=size
        )

    async def get_note(self, campaign_id: int, note_id: int, current_user: UserResponse) -> CampaignNoteResponse:
        """One note."""

        await self._gm(campaign_id, current_user)
        return CampaignNoteResponse.model_validate(await self._get_or_404(campaign_id, note_id))

    async def create(
        self, campaign_id: int, data: CampaignNoteCreate, current_user: UserResponse
    ) -> CampaignNoteResponse:
        """Add a note."""

        await self._gm(campaign_id, current_user)
        async with self._atomic():
            note = await self.repository.create({**data.model_dump(), "campaign_id": campaign_id})
            note_id = note.id

        return CampaignNoteResponse.model_validate(await self._get_or_404(campaign_id, note_id))

    async def update(
        self, campaign_id: int, note_id: int, data: CampaignNoteUpdate, current_user: UserResponse
    ) -> CampaignNoteResponse:
        """Change a note."""

        await self._gm(campaign_id, current_user)
        async with self._atomic():
            note = await self._get_or_404(campaign_id, note_id)
            await self.repository.update(note, data.model_dump(exclude_unset=True))

        return CampaignNoteResponse.model_validate(await self._get_or_404(campaign_id, note_id))

    async def delete(self, campaign_id: int, note_id: int, current_user: UserResponse) -> None:
        """Delete a note."""

        await self._gm(campaign_id, current_user)
        async with self._atomic():
            await self.repository.delete(await self._get_or_404(campaign_id, note_id))

    async def _get_or_404(self, campaign_id: int, note_id: int) -> CampaignNote:
        note = await self.repository.get_in_campaign(campaign_id, note_id)
        if note is None:
            raise CampaignNoteNotFoundException(campaign_id, note_id)

        return note
