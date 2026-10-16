"""Character repository: base CRUD plus owner/campaign scoping, row locking and HP updates."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.constants import CampaignCharacterStatus
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.models.character.character_model import Character


class CharacterRepository(BaseRepository[Character]):
    """
    Repository for the ``Character`` model: inherits the full base CRUD
    and pins ``search`` to ``name`` only. Sub-domain collections
    (proficiencies, spells, conditions, feats/features, items) are not
    eager-loaded — each is served by its own sub-domain endpoint.
    """

    def __init__(self, db: AsyncSession):
        """Configure the repository's search fields."""

        super().__init__(
            Character,
            db,
            search_fields=["name"],
        )

    async def get_owner_id(self, character_id: int) -> int | None:
        """Return the character's ``owner_id``, or ``None`` when it does not exist."""

        return await self.db.scalar(select(Character.owner_id).where(Character.id == character_id))

    async def is_managed_by(self, character_id: int, gm_id: int) -> bool:
        """Whether the character is ``ACTIVE`` in a campaign owned by ``gm_id`` (the campaign GM's sheet access)."""

        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        CampaignCharacter.character_id == character_id,
                        CampaignCharacter.status == CampaignCharacterStatus.ACTIVE,
                        CampaignCharacter.campaign_id == Campaign.id,
                        Campaign.owner_id == gm_id,
                    )
                )
            )
        )

    @staticmethod
    def managed_by_condition(gm_id: int) -> Any:
        """WHERE clause: characters ``ACTIVE`` in one of ``gm_id``'s campaigns (``scope=all`` for a GM)."""

        return Character.id.in_(
            select(CampaignCharacter.character_id)
            .join(Campaign, Campaign.id == CampaignCharacter.campaign_id)
            .where(Campaign.owner_id == gm_id, CampaignCharacter.status == CampaignCharacterStatus.ACTIVE)
        )

    async def count_where(
        self, *, filters: dict[str, Any] | None = None, search: str | None = None, conditions: Sequence[Any] = ()
    ) -> int:
        """``count`` plus extra WHERE clauses (the base ``count`` takes only ``filters``/``search``)."""

        stmt = select(func.count()).select_from(Character)
        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_search(stmt, search)

        return (await self.db.scalar(stmt.where(*conditions))) or 0

    async def get_by_id_light(self, model_id: int) -> Character | None:
        """
        Fetch a ``Character`` without ``populate_existing``: an instance
        already present in the session is returned as it is in memory.
        """

        result = await self.db.execute(select(Character).where(Character.id == model_id))
        return result.scalar_one_or_none()

    async def get_for_update(self, character_id: int) -> Character | None:
        """
        Fetch the character row with ``SELECT ... FOR UPDATE`` (attributes
        refreshed), serializing concurrent read-modify-write flows such as
        HP changes until the surrounding transaction ends.
        """

        return await self.db.scalar(
            select(Character)
            .where(Character.id == character_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def update_hp(self, character: Character, current_hp: int, temp_hp: int) -> Character:
        """Set current and temp HP directly (flush only). Bounds/validation happen in the service."""

        character.current_hp = current_hp
        character.temp_hp = temp_hp
        await self.flush()
        return character
