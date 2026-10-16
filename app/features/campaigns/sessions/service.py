"""
Campaign sessions: the table's schedule and archive, attendance, and the GM's chronicle.

Players see every session of their campaign (when, what, who attended); the chronicle opens to them only once the
GM publishes it, without the ``:::gm`` blocks (the same syntax and stripper as articles). ``GET /campaigns/schedule``
lists the dated sessions of every campaign the caller runs or plays in.
"""

from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CampaignSessionStatus
from app.core.exceptions import RecordIdsInvalidError
from app.core.pagination import Page, paginate
from app.features.campaigns.access import CampaignContext
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.exceptions import CampaignSessionNotFoundException
from app.features.campaigns.sessions.repository import CampaignSessionsRepository
from app.features.campaigns.sessions.schemas import (
    CampaignSessionBrief,
    CampaignSessionCreate,
    CampaignSessionResponse,
    CampaignSessionUpdate,
    ScheduleEntry,
    SessionAttendanceUpdate,
    SessionAttendee,
    as_utc,
)
from app.features.shared.secrets import strip_gm_blocks
from app.features.users.schemas import UserResponse
from app.models.campaigns.campaign_session_model import CampaignSession


def _attendee(row: Any) -> SessionAttendee:
    return SessionAttendee(
        participation_id=row.participation_id,
        character_id=row.character_id,
        character_name=row.character_name,
        owner={"id": row.owner_id, "username": row.owner_username},
    )


class CampaignSessionsService(CampaignScopedService):
    """Session list/read and the schedule (GM and players), and the GM's writes."""

    repository: CampaignSessionsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the sessions repository."""

        super().__init__(CampaignSessionsRepository(db))

    async def list_sessions(
        self,
        campaign_id: int,
        current_user: UserResponse,
        *,
        status: CampaignSessionStatus | None,
        page: int,
        size: int,
    ) -> Page[CampaignSessionBrief]:
        """The campaign's sessions by number with their attendance (``status=played``: the archive)."""

        await self._reader(campaign_id, current_user)
        skip, limit = paginate(page, size)
        sessions, total = await self.repository.list_for_campaign(campaign_id, status=status, skip=skip, limit=limit)
        attendees = await self.repository.attendees_by_session([session.id for session in sessions])
        items = [
            CampaignSessionBrief.model_validate(session).model_copy(
                update={"attendees": [_attendee(row) for row in attendees.get(session.id, [])]}
            )
            for session in sessions
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def get_session(
        self, campaign_id: int, session_id: int, current_user: UserResponse
    ) -> CampaignSessionResponse:
        """One session in the caller's view (players: no chronicle until it is published)."""

        ctx = await self._reader(campaign_id, current_user)
        return await self._response(await self._get_or_404(ctx, session_id), ctx)

    async def schedule(
        self,
        current_user: UserResponse,
        *,
        role: Literal["gm", "player"] | None = None,
        starts_from: datetime | None,
        until: datetime | None,
        include_cancelled: bool,
        page: int,
        size: int,
    ) -> Page[ScheduleEntry]:
        """
        Dated sessions of the caller's campaigns from ``starts_from`` (default: now) on: the ones they run
        (``role=gm``), play in (``role=player``) or both.
        """

        skip, limit = paginate(page, size)
        rows, total = await self.repository.schedule(
            current_user.id,
            role=role,
            starts_from=as_utc(starts_from) or self.clock(),
            until=as_utc(until),
            include_cancelled=include_cancelled,
            skip=skip,
            limit=limit,
        )
        items = [
            ScheduleEntry(
                id=row.id,
                number=row.number,
                title=row.title,
                status=row.status,
                scheduled_at=row.scheduled_at,
                campaign={"id": row.campaign_id, "title": row.campaign_title},
                viewer_role="gm" if row.is_owner else "player",
            )
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def create(
        self, campaign_id: int, data: CampaignSessionCreate, current_user: UserResponse
    ) -> CampaignSessionResponse:
        """Add a session (GM); a duplicate ``number`` is a 409 from the unique constraint."""

        ctx = await self._gm(campaign_id, current_user)
        fields = data.model_dump()
        async with self._atomic():
            if fields["number"] is None:
                await self.repository.lock_campaign(campaign_id)  # two auto-numbered creates can't take one number
                fields["number"] = await self.repository.next_number(campaign_id)
            session = await self.repository.create({**fields, "campaign_id": campaign_id})
            session_id = session.id

        return await self._response(await self._get_or_404(ctx, session_id), ctx)

    async def update(
        self, campaign_id: int, session_id: int, data: CampaignSessionUpdate, current_user: UserResponse
    ) -> CampaignSessionResponse:
        """Partial update (GM). Editing a published chronicle keeps it published."""

        ctx = await self._gm(campaign_id, current_user)
        async with self._atomic():
            session = await self._get_or_404(ctx, session_id)
            await self.repository.update(session, data.model_dump(exclude_unset=True))

        return await self._response(await self._get_or_404(ctx, session_id), ctx)

    async def set_attendance(
        self, campaign_id: int, session_id: int, data: SessionAttendanceUpdate, current_user: UserResponse
    ) -> CampaignSessionResponse:
        """
        Replace who attended the session (GM). Any participation of this campaign counts, ended ones included.

        Raises:
            RecordIdsInvalidError: an id isn't a participation of this campaign (400).
        """

        ctx = await self._gm(campaign_id, current_user)
        participation_ids = list(dict.fromkeys(data.participation_ids))
        known = await self.repository.participation_ids_in_campaign(campaign_id, participation_ids)
        missing = sorted(set(participation_ids) - known)
        if missing:
            raise RecordIdsInvalidError("Campaign characters", missing)

        async with self._atomic():
            await self.repository.set_attendance(await self._get_or_404(ctx, session_id), participation_ids)

        return await self._response(await self._get_or_404(ctx, session_id), ctx)

    async def set_published(
        self, campaign_id: int, session_id: int, published: bool, current_user: UserResponse
    ) -> CampaignSessionResponse:
        """Publish (players read the chronicle from now on) or unpublish it (GM). Re-publishing keeps the first date."""

        ctx = await self._gm(campaign_id, current_user)
        async with self._atomic():
            session = await self._get_or_404(ctx, session_id)
            if published and session.published_at is None:
                await self.repository.update(session, {"published_at": self.clock()})
            elif not published and session.published_at is not None:
                await self.repository.update(session, {"published_at": None})

        return await self._response(await self._get_or_404(ctx, session_id), ctx)

    async def delete(self, campaign_id: int, session_id: int, current_user: UserResponse) -> None:
        """Delete a session with its attendance and reviews (GM)."""

        ctx = await self._gm(campaign_id, current_user)
        async with self._atomic():
            await self.repository.delete(await self._get_or_404(ctx, session_id))

    async def _get_or_404(self, ctx: CampaignContext, session_id: int) -> CampaignSession:
        """The session of ``ctx``'s campaign, else 404."""

        session = await self.repository.get_in_campaign(ctx.campaign_id, session_id)
        if session is None:
            raise CampaignSessionNotFoundException(ctx.campaign_id, session_id)

        return session

    async def _response(self, session: CampaignSession, ctx: CampaignContext) -> CampaignSessionResponse:
        """Serialize with attendance; players get no chronicle before publication and no ``:::gm`` blocks after."""

        response = CampaignSessionResponse.model_validate(session)
        attendees = await self.repository.attendees_by_session([session.id])
        response.attendees = [_attendee(row) for row in attendees.get(session.id, [])]
        if not ctx.is_gm:
            published = session.published_at is not None
            response.chronicle_markdown = (strip_gm_blocks(response.chronicle_markdown) or "") if published else None

        return response
