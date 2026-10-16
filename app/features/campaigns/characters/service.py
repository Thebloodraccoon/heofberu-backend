"""
A campaign's roster: the GM adds free characters and changes their status; players read the roster.

The player is neither asked nor notified and can't leave: the roster is entirely the GM's. A character is in one
campaign at a time (``ACTIVE``); ``dead``/``retired``/``removed`` free it. ``removed`` also takes away the
player's read access (unless another of their characters is still in the campaign).
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CAMPAIGN_CLOSED_STATUSES, CampaignCharacterStatus
from app.core.exceptions import RecordNotFoundError
from app.core.pagination import Page, paginate
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.characters.repository import CampaignCharactersRepository
from app.features.campaigns.characters.schemas import (
    CampaignCharacterAdd,
    CampaignCharacterResponse,
    CampaignCharacterStatusUpdate,
    CharacterCandidate,
)
from app.features.campaigns.exceptions import (
    CampaignCharacterNotFoundException,
    CampaignCharacterStatusException,
    CampaignClosedException,
    CharacterNotFreeException,
)
from app.features.users.schemas import UserResponse


def _brief(row: Any) -> dict:
    """Nest a roster/candidate row's flat character and owner columns."""

    return {
        "character": {
            "id": row.character_id,
            "name": row.name,
            "level": row.level,
            "class_name": row.class_name,
            "race_name": row.race_name,
        },
        "owner": {"id": row.owner_id, "username": row.owner_username},
    }


def status_change_allowed(current: CampaignCharacterStatus, target: CampaignCharacterStatus) -> bool:
    """
    The roster's status rule: an ``active`` participation may become ``dead``/``retired``/``removed``, any
    participation may become ``removed``, and nothing goes back to ``active`` (that is a new participation, so the
    history stays intact). Setting the current status again is a no-op, not a change.
    """

    if current == target:
        return True
    if target == CampaignCharacterStatus.ACTIVE:
        return False

    return current == CampaignCharacterStatus.ACTIVE or target == CampaignCharacterStatus.REMOVED


def _roster_item(row: Any) -> CampaignCharacterResponse:
    return CampaignCharacterResponse(
        id=row.id, status=row.status, joined_at=row.joined_at, ended_at=row.ended_at, **_brief(row)
    )


class CampaignCharactersService(CampaignScopedService):
    """Roster reads (GM and players), candidate search, add and status changes (GM)."""

    repository: CampaignCharactersRepository

    def __init__(self, db: AsyncSession):
        """Initialize the roster repository."""

        super().__init__(CampaignCharactersRepository(db))

    async def list_roster(
        self, campaign_id: int, current_user: UserResponse, *, page: int, size: int
    ) -> Page[CampaignCharacterResponse]:
        """The roster: the GM also sees removed participations (history), players don't."""

        ctx = await self._reader(campaign_id, current_user)
        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_roster(campaign_id, include_removed=ctx.is_gm, skip=skip, limit=limit)
        return Page(items=[_roster_item(row) for row in rows], total=total, page=page, size=size)

    async def search_candidates(
        self,
        campaign_id: int,
        current_user: UserResponse,
        *,
        player: str | None,
        query: str | None,
        page: int,
        size: int,
    ) -> Page[CharacterCandidate]:
        """Free characters by player username and/or character name (GM). Only the brief card, never the sheet."""

        await self._gm(campaign_id, current_user)
        skip, limit = paginate(page, size)
        rows, total = await self.repository.search_free(player=player, query=query, skip=skip, limit=limit)
        items = [CharacterCandidate(**_brief(row)["character"], owner=_brief(row)["owner"]) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def add(
        self, campaign_id: int, data: CampaignCharacterAdd, current_user: UserResponse
    ) -> CampaignCharacterResponse:
        """
        Add a free character (GM). From now on the GM manages its sheet (see ``characters/access.py``).

        Raises:
            CampaignClosedException: the campaign is finished, abandoned or archived (409).
            RecordNotFoundError: no such character (404).
            CharacterNotFreeException: the character is active in a campaign, this one included (409).
        """

        async with self._atomic():
            # The lock keeps a concurrent close/archive from releasing characters before this row exists.
            await self._gm(campaign_id, current_user, lock=True)
            state = await self.repository.campaign_state(campaign_id)
            if state.status in CAMPAIGN_CLOSED_STATUSES or state.archived_at is not None:
                raise CampaignClosedException(campaign_id)

            owner_id = await self.repository.get_character_owner(data.character_id)
            if owner_id is None:
                raise RecordNotFoundError("Character", str(data.character_id))
            if await self.repository.is_active_somewhere(data.character_id):
                raise CharacterNotFreeException(data.character_id)

            participation_id = await self.repository.add(campaign_id, data.character_id, owner_id)

        return _roster_item(await self.repository.get_roster_row(participation_id))

    async def set_status(
        self, campaign_id: int, participation_id: int, data: CampaignCharacterStatusUpdate, current_user: UserResponse
    ) -> CampaignCharacterResponse:
        """
        Change a participation's status (GM). Allowed: an ``active`` one to ``dead``/``retired``/``removed``, and any
        one to ``removed``. Back to ``active`` is a new participation (``POST``), so the history stays intact.
        """

        async with self._atomic():
            await self._gm(campaign_id, current_user, lock=True)
            participation = await self.repository.get_participation(campaign_id, participation_id)
            if participation is None:
                raise CampaignCharacterNotFoundException(campaign_id, participation_id)

            current, target = participation.status, data.status
            if not status_change_allowed(current, target):
                raise CampaignCharacterStatusException(participation_id, current.value, target.value)

            if current != target:
                participation.status = target
                if participation.ended_at is None:
                    participation.ended_at = self.clock()
                await self.repository.flush()

        return _roster_item(await self.repository.get_roster_row(participation_id))
