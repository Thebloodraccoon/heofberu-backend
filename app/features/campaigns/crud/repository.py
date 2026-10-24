"""Campaign CRUD queries: the campaign row, "my campaigns" and releasing characters."""

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.constants import CampaignCharacterStatus, PublicCampaignStatus
from app.core.base.repository import BaseRepository
from app.core.pagination import fetch_page
from app.features.campaigns.base import CampaignAccessMixin, player_condition
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.models.campaigns.public_campaign_model import PublicCampaign
from app.models.character.character_model import Character


class CampaignRepository(CampaignAccessMixin, BaseRepository[Campaign]):
    """``Campaign`` rows with their owner (joined by the model) and preset link eager-loaded."""

    def __init__(self, db: AsyncSession):
        """Bind to ``Campaign``; not searchable by the generic search (listing has its own filters)."""

        super().__init__(Campaign, db, default_load_options=[joinedload(Campaign.public_campaign)], search_fields=[])

    async def list_for_user(
        self,
        user_id: int,
        *,
        all_campaigns: bool,
        role: str | None,
        include_archived: bool,
        skip: int,
        limit: int,
        query: str | None = None,
    ) -> tuple[list[Any], int]:
        """
        One page of campaigns the user owns or plays in (``all_campaigns``: every campaign, founder only), newest
        activity first. Each row is ``(Campaign, is_player)``; the total comes from ``count() OVER()``.
        """

        is_player = player_condition(user_id)
        conditions: list[Any] = []
        if not all_campaigns:
            if role == "gm":
                conditions.append(Campaign.owner_id == user_id)
            elif role == "player":
                conditions.append(is_player)
            else:
                conditions.append(or_(Campaign.owner_id == user_id, is_player))
        if not include_archived:
            conditions.append(Campaign.archived_at.is_(None))
        if query and query.strip():
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(Campaign.title.ilike(f"%{escaped}%", escape="\\"))

        return await fetch_page(
            self.db,
            select(Campaign, is_player.label("is_player"))
            .options(joinedload(Campaign.public_campaign))
            .where(*conditions)
            .order_by(Campaign.updated_at.desc(), Campaign.id.desc()),
            skip=skip,
            limit=limit,
        )

    async def my_characters(self, user_id: int, campaign_ids: list[int]) -> dict[int, list[Any]]:
        """The user's own participations (not ``REMOVED``) in each of ``campaign_ids``, by join time, in one query."""

        if not campaign_ids:
            return {}

        result = await self.db.execute(
            select(
                CampaignCharacter.campaign_id,
                CampaignCharacter.id.label("participation_id"),
                Character.id.label("character_id"),
                Character.name,
                CampaignCharacter.status,
            )
            .join(Character, Character.id == CampaignCharacter.character_id)
            .where(
                CampaignCharacter.user_id == user_id,
                CampaignCharacter.campaign_id.in_(campaign_ids),
                CampaignCharacter.status != CampaignCharacterStatus.REMOVED,
            )
            .order_by(CampaignCharacter.joined_at, CampaignCharacter.id)
        )
        grouped: dict[int, list[Any]] = defaultdict(list)
        for row in result:
            grouped[row.campaign_id].append(row)

        return grouped

    async def get_public_campaign(self, public_campaign_id: int, *, include_unpublished: bool) -> PublicCampaign | None:
        """The preset a campaign is made from / linked to; unpublished ones only with ``include_unpublished``."""

        stmt = select(PublicCampaign).where(PublicCampaign.id == public_campaign_id)
        if not include_unpublished:
            stmt = stmt.where(PublicCampaign.status == PublicCampaignStatus.PUBLISHED)

        return await self.db.scalar(stmt)

    async def release_characters(self, campaign_id: int, ended_at: datetime) -> list[int]:
        """Retire every ``ACTIVE`` participation of the campaign (frees the characters); returns their character ids."""

        result = await self.db.execute(
            update(CampaignCharacter)
            .where(
                CampaignCharacter.campaign_id == campaign_id,
                CampaignCharacter.status == CampaignCharacterStatus.ACTIVE,
            )
            .values(status=CampaignCharacterStatus.RETIRED, ended_at=ended_at)
            .returning(CampaignCharacter.character_id)
        )
        await self.flush()
        return list(result.scalars())
