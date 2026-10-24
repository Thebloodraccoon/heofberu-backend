"""GM note queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.core.pagination import fetch_page
from app.features.campaigns.base import CampaignAccessMixin
from app.models.campaigns.campaign_note_model import CampaignNote


class CampaignNotesRepository(CampaignAccessMixin, BaseRepository[CampaignNote]):
    """Notes of one campaign."""

    def __init__(self, db: AsyncSession):
        """Bind to ``CampaignNote``."""

        super().__init__(CampaignNote, db, search_fields=[])

    async def list_for_campaign(self, campaign_id: int, *, skip: int, limit: int) -> tuple[list[CampaignNote], int]:
        """One page of the campaign's notes, most recently updated first, and the total."""

        rows, total = await fetch_page(
            self.db,
            select(CampaignNote)
            .where(CampaignNote.campaign_id == campaign_id)
            .order_by(CampaignNote.updated_at.desc(), CampaignNote.id.desc()),
            skip=skip,
            limit=limit,
        )
        return [row.CampaignNote for row in rows], total

    async def get_in_campaign(self, campaign_id: int, note_id: int) -> CampaignNote | None:
        """The note if it belongs to the campaign."""

        return await self.db.scalar(
            select(CampaignNote)
            .where(CampaignNote.id == note_id, CampaignNote.campaign_id == campaign_id)
            .execution_options(populate_existing=True)
        )
