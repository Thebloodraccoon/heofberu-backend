"""Campaign session queries: the session list, attendance and the cross-campaign schedule."""

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CampaignSessionStatus
from app.core.base.repository import BaseRepository
from app.core.pagination import fetch_page
from app.features.campaigns.base import CampaignAccessMixin, player_condition
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.models.campaigns.campaign_session_attendance_model import CampaignSessionAttendance
from app.models.campaigns.campaign_session_model import CampaignSession
from app.models.character.character_model import Character
from app.models.user_model import User


class CampaignSessionsRepository(CampaignAccessMixin, BaseRepository[CampaignSession]):
    """Sessions of one campaign with their attendance, plus the schedule across the caller's campaigns."""

    def __init__(self, db: AsyncSession):
        """Bind to ``CampaignSession`` (not searchable by the generic search)."""

        super().__init__(CampaignSession, db, search_fields=[])

    async def list_for_campaign(
        self, campaign_id: int, *, status: CampaignSessionStatus | None, skip: int, limit: int
    ) -> tuple[list[CampaignSession], int]:
        """One page of the campaign's sessions by number, optionally of one ``status`` (``played`` = the archive)."""

        stmt = select(CampaignSession).where(CampaignSession.campaign_id == campaign_id)
        if status is not None:
            stmt = stmt.where(CampaignSession.status == status)

        rows, total = await fetch_page(self.db, stmt.order_by(CampaignSession.number), skip=skip, limit=limit)
        return [row.CampaignSession for row in rows], total

    async def get_in_campaign(self, campaign_id: int, session_id: int) -> CampaignSession | None:
        """The session if it belongs to the campaign."""

        stmt = select(CampaignSession).where(
            CampaignSession.id == session_id, CampaignSession.campaign_id == campaign_id
        )
        return await self.db.scalar(stmt.execution_options(populate_existing=True))

    async def next_number(self, campaign_id: int) -> int:
        """One past the campaign's highest session number (1 for the first session)."""

        current = await self.db.scalar(
            select(func.max(CampaignSession.number)).where(CampaignSession.campaign_id == campaign_id)
        )
        return (current or 0) + 1

    async def attendees_by_session(self, session_ids: list[int]) -> dict[int, list[Any]]:
        """Attendance rows (participation, character, player) of every given session in one query, by name."""

        if not session_ids:
            return {}

        result = await self.db.execute(
            select(
                CampaignSessionAttendance.session_id,
                CampaignSessionAttendance.participation_id,
                Character.id.label("character_id"),
                Character.name.label("character_name"),
                User.id.label("owner_id"),
                User.username.label("owner_username"),
            )
            .join(CampaignCharacter, CampaignCharacter.id == CampaignSessionAttendance.participation_id)
            .join(Character, Character.id == CampaignCharacter.character_id)
            .join(User, User.id == CampaignCharacter.user_id)
            .where(CampaignSessionAttendance.session_id.in_(session_ids))
            .order_by(Character.name, CampaignSessionAttendance.participation_id)
        )
        grouped: dict[int, list[Any]] = defaultdict(list)
        for row in result:
            grouped[row.session_id].append(row)

        return grouped

    async def participation_ids_in_campaign(self, campaign_id: int, participation_ids: list[int]) -> set[int]:
        """Which of ``participation_ids`` are participations of this campaign (any status: history counts)."""

        if not participation_ids:
            return set()

        return set(
            await self.db.scalars(
                select(CampaignCharacter.id).where(
                    CampaignCharacter.campaign_id == campaign_id, CampaignCharacter.id.in_(participation_ids)
                )
            )
        )

    async def set_attendance(self, session: CampaignSession, participation_ids: list[int]) -> None:
        """Replace the session's attendance (flush only)."""

        await self.replace_association(
            CampaignSessionAttendance.__table__, session, "session_id", "participation_id", participation_ids
        )

    async def schedule(
        self,
        user_id: int,
        *,
        role: str | None,
        starts_from: datetime,
        until: datetime | None,
        include_cancelled: bool,
        skip: int,
        limit: int,
    ) -> tuple[list[Any], int]:
        """
        One page of dated sessions in the campaigns ``user_id`` runs or plays in (archived campaigns left out),
        soonest first. Rows carry the campaign and ``is_owner``; the total comes from ``count() OVER()``.
        """

        relation = {"gm": Campaign.owner_id == user_id, "player": player_condition(user_id)}
        conditions: list[Any] = [
            relation.get(role, or_(Campaign.owner_id == user_id, player_condition(user_id))),
            Campaign.archived_at.is_(None),
            CampaignSession.scheduled_at >= starts_from,
        ]
        if until is not None:
            conditions.append(CampaignSession.scheduled_at < until)
        if not include_cancelled:
            conditions.append(CampaignSession.status != CampaignSessionStatus.CANCELLED)

        stmt = (
            select(
                CampaignSession.id,
                CampaignSession.number,
                CampaignSession.title,
                CampaignSession.status,
                CampaignSession.scheduled_at,
                Campaign.id.label("campaign_id"),
                Campaign.title.label("campaign_title"),
                (Campaign.owner_id == user_id).label("is_owner"),
            )
            .join(Campaign, Campaign.id == CampaignSession.campaign_id)
            .where(*conditions)
            .order_by(CampaignSession.scheduled_at, CampaignSession.id)
        )
        return await fetch_page(self.db, stmt, skip=skip, limit=limit)
