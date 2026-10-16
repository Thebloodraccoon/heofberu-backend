"""Roster queries: participations, free-character search and the one-active-campaign rule."""

from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from app.constants import CampaignCharacterStatus
from app.core.base.repository import SessionRepository
from app.core.db_errors import constraint_name
from app.core.pagination import fetch_page
from app.features.campaigns.base import CampaignAccessMixin
from app.features.campaigns.exceptions import CharacterNotFreeException
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.models.character.character_model import Character
from app.models.classes.class_model import Class
from app.models.races.race_model import Race
from app.models.user_model import User

ONE_ACTIVE_CONSTRAINT = "uq_campaign_characters_one_active"


def _brief_columns() -> list[Any]:
    """Character brief + owner columns shared by the roster and the candidate search."""

    return [
        Character.id.label("character_id"),
        Character.name,
        Character.level,
        Class.name.label("class_name"),
        Race.name.label("race_name"),
        User.id.label("owner_id"),
        User.username.label("owner_username"),
    ]


def _with_brief_joins(stmt: Any) -> Any:
    """Join class, race and owner onto a statement already selecting from ``characters``."""

    return (
        stmt.join(Class, Class.id == Character.class_id)
        .join(User, User.id == Character.owner_id)
        .outerjoin(Race, Race.id == Character.race_id)
    )


def _is_active_somewhere() -> Any:
    """EXISTS: the character has an ``ACTIVE`` participation (it isn't free)."""

    return exists().where(
        CampaignCharacter.character_id == Character.id, CampaignCharacter.status == CampaignCharacterStatus.ACTIVE
    )


class CampaignCharactersRepository(CampaignAccessMixin, SessionRepository):
    """Participations of one campaign and the characters that could join it."""

    async def campaign_state(self, campaign_id: int) -> Any:
        """``(status, archived_at)`` of the campaign (it is known to exist once the context resolved)."""

        return (
            await self.db.execute(select(Campaign.status, Campaign.archived_at).where(Campaign.id == campaign_id))
        ).first()

    async def list_roster(
        self, campaign_id: int, *, include_removed: bool, skip: int, limit: int
    ) -> tuple[list[Any], int]:
        """One page of participation rows (with character brief and owner) by join time, and the total."""

        stmt = _with_brief_joins(
            select(
                CampaignCharacter.id,
                CampaignCharacter.status,
                CampaignCharacter.joined_at,
                CampaignCharacter.ended_at,
                *_brief_columns(),
            ).join(Character, Character.id == CampaignCharacter.character_id)
        ).where(CampaignCharacter.campaign_id == campaign_id)
        if not include_removed:
            stmt = stmt.where(CampaignCharacter.status != CampaignCharacterStatus.REMOVED)

        return await fetch_page(
            self.db, stmt.order_by(CampaignCharacter.joined_at, CampaignCharacter.id), skip=skip, limit=limit
        )

    async def search_free(
        self, *, player: str | None, query: str | None, skip: int, limit: int
    ) -> tuple[list[Any], int]:
        """
        Free characters (no ``ACTIVE`` participation) matching the owner's username and/or the character name
        (case-insensitive substring), by name. Returns the page and the total match count.
        """

        conditions: list[Any] = [~_is_active_somewhere()]
        if player:
            conditions.append(User.username.ilike(f"%{_escape_like(player)}%", escape="\\"))
        if query:
            conditions.append(Character.name.ilike(f"%{_escape_like(query)}%", escape="\\"))

        stmt = _with_brief_joins(select(*_brief_columns()).select_from(Character))
        return await fetch_page(
            self.db, stmt.where(*conditions).order_by(Character.name, Character.id), skip=skip, limit=limit
        )

    async def get_character_owner(self, character_id: int) -> int | None:
        """The character's owner id, or ``None`` when the character doesn't exist."""

        return await self.db.scalar(select(Character.owner_id).where(Character.id == character_id))

    async def is_active_somewhere(self, character_id: int) -> bool:
        """Whether the character already plays in a campaign."""

        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        CampaignCharacter.character_id == character_id,
                        CampaignCharacter.status == CampaignCharacterStatus.ACTIVE,
                    )
                )
            )
        )

    async def add(self, campaign_id: int, character_id: int, user_id: int) -> int:
        """
        Insert an ``ACTIVE`` participation and return its id.

        The partial unique index decides races between two GMs adding the same character: the loser gets
        ``CharacterNotFreeException`` (409) instead of a generic integrity error.
        """

        row = CampaignCharacter(campaign_id=campaign_id, character_id=character_id, user_id=user_id)
        self.db.add(row)
        try:
            await self.flush()
        except IntegrityError as exc:
            if constraint_name(exc) == ONE_ACTIVE_CONSTRAINT:
                raise CharacterNotFreeException(character_id) from None
            raise

        return row.id

    async def get_participation(self, campaign_id: int, participation_id: int) -> CampaignCharacter | None:
        """The participation row, only if it belongs to the campaign."""

        return await self.db.scalar(
            select(CampaignCharacter).where(
                CampaignCharacter.id == participation_id, CampaignCharacter.campaign_id == campaign_id
            )
        )

    async def get_roster_row(self, participation_id: int) -> Any:
        """One roster row (same shape as ``list_roster``)."""

        stmt = _with_brief_joins(
            select(
                CampaignCharacter.id,
                CampaignCharacter.status,
                CampaignCharacter.joined_at,
                CampaignCharacter.ended_at,
                *_brief_columns(),
            ).join(Character, Character.id == CampaignCharacter.character_id)
        ).where(CampaignCharacter.id == participation_id)
        return (await self.db.execute(stmt)).first()


def _escape_like(value: str) -> str:
    """Escape ``LIKE`` wildcards so a username like ``a_b`` matches literally."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
