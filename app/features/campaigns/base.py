"""Thin bases shared by the campaign capabilities: the access lookup and the context-resolving service."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CampaignCharacterStatus
from app.core.base.repository import RepositoryMixin
from app.core.base.transaction import TransactionMixin
from app.features.campaigns.access import CampaignContext
from app.features.campaigns.exceptions import CampaignNotFoundException
from app.features.users.schemas import UserResponse
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.settings._common import aware_utcnow


def player_condition(user_id: int, campaign_id_column: Any = Campaign.id) -> Any:
    """EXISTS clause: ``user_id`` has a character in the campaign whose participation isn't ``REMOVED``."""

    return exists().where(
        CampaignCharacter.campaign_id == campaign_id_column,
        CampaignCharacter.user_id == user_id,
        CampaignCharacter.status != CampaignCharacterStatus.REMOVED,
    )


class CampaignAccessMixin(RepositoryMixin):
    """``access_row`` and ``lock_campaign`` for every campaign repository (needs ``self.db``)."""

    async def access_row(self, campaign_id: int, user_id: int) -> Any:
        """``(owner_id, is_player)`` of the campaign for ``user_id`` in one query, or ``None`` if it doesn't exist."""

        result = await self.db.execute(
            select(Campaign.owner_id, player_condition(user_id).label("is_player")).where(Campaign.id == campaign_id)
        )
        return result.first()

    async def lock_campaign(self, campaign_id: int) -> None:
        """
        ``SELECT ... FOR UPDATE`` on the campaign row, inside the caller's transaction. Serializes the writes that
        read campaign state and then act on it: adding a character vs. closing/archiving (which releases active
        characters), and auto-numbering sessions.
        """

        await self.db.execute(select(Campaign.id).where(Campaign.id == campaign_id).with_for_update())


class CampaignScopedService(TransactionMixin):
    """
    Base of every campaign capability service: resolves the caller's ``CampaignContext`` (404 when the campaign
    doesn't exist) and owns the transaction helpers. Capabilities then call ``ctx.ensure_*`` for their rule.
    """

    repository: Any
    #: Source of "now" for every timestamp the campaign services write (``ended_at``, ``archived_at``,
    #: ``published_at``, ``edited_at``, ``hidden_at``) and the schedule's default window. Tests pin it per instance.
    clock: Callable[[], datetime] = staticmethod(aware_utcnow)

    def __init__(self, repository: Any):
        """Keep the capability repository (it must include ``CampaignAccessMixin``)."""

        self.repository = repository

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def _context(self, campaign_id: int, user: UserResponse) -> CampaignContext:
        """The caller's standing in the campaign (not yet checked against any rule)."""

        row = await self.repository.access_row(campaign_id, user.id)
        if row is None:
            raise CampaignNotFoundException(campaign_id)

        return CampaignContext.of(user, campaign_id, row.owner_id, bool(row.is_player))

    async def _reader(self, campaign_id: int, user: UserResponse) -> CampaignContext:
        """Context of a caller who may read the campaign (GM, founder or player), else 404."""

        return (await self._context(campaign_id, user)).ensure_can_read()

    async def _gm(self, campaign_id: int, user: UserResponse) -> CampaignContext:
        """Context of the campaign's GM or the founder, else 404/403."""

        return (await self._context(campaign_id, user)).ensure_gm()

    async def _player(self, campaign_id: int, user: UserResponse) -> CampaignContext:
        """Context of a player of the campaign, else 404/403."""

        return (await self._context(campaign_id, user)).ensure_player()

    async def _reviewer(self, campaign_id: int, user: UserResponse) -> CampaignContext:
        """Context of a player who may review the campaign (not its own GM), else 404/403."""

        return (await self._context(campaign_id, user)).ensure_reviewer()
