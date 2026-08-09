"""Repository for a character's effective ability scores and derived combat stats."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.constants import ItemType
from app.core.base_repository import BaseRepository
from app.features.characters.ability_score.calculator import ArmorSpec
from app.models import (
    CharacterAbilityScore,
    CharacterItem,
    Class,
    Item,
    Race,
)
from app.models.character_association_models import CharacterFeat
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus


class CharacterStatsRepository(BaseRepository[CharacterAbilityScore]):
    """
    Repository backing ``CharacterStatsService``: the ``character_ability_scores``
    cache table plus the reference-data queries the derived combat stats need.

    Split out of ``CharacterRepository`` — the cache table is a
    derived/cached table (effective ability scores after race/feat bonuses),
    distinct from both the base ``Character`` row and from
    ``CharacterAbilityScoreCalculator`` (which computes the values but
    never persists them itself). See ``CharacterStatsService`` for the
    single point that decides *when* to recompute + persist.

    Also owns the source-bonus queries the calculator needs
    (``get_race_bonuses`` / ``get_feat_increases``) — these moved here
    from the old calculator so it could become fully pure (no ``Session``).

    The derived combat stats (hit dice, speed, armor class) load their
    references (class, race, equipped armor) through the same batch
    queries, so a listing page costs a constant number of queries.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterAbilityScore, db)

    async def get_by_character_id(self, character_id: int) -> CharacterAbilityScore | None:
        """Fetch the cached effective-ability-score row, or None if never computed."""

        result = await self.db.execute(
            select(CharacterAbilityScore).where(CharacterAbilityScore.character_id == character_id)
        )
        return result.scalar_one_or_none()

    async def get_many_by_character_ids(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """
        Fetch the cache rows for many characters in a single query,
        keyed by ``character_id``. Empty input returns ``{}``.

        This is what lets ``CharacterService.get_characters`` attach
        cached ability scores to a whole listing page in one query
        instead of one ``get_by_character_id`` per row (the old N+1).
        """

        if not character_ids:
            return {}

        result = await self.db.execute(
            select(CharacterAbilityScore).where(CharacterAbilityScore.character_id.in_(character_ids))
        )
        return {row.character_id: row for row in result.scalars().unique().all()}

    async def get_race_bonuses(self, race_id: int | None) -> list[RaceAbilityBonus]:
        """Fetch a race's ability bonuses, or ``[]`` for a character with no race."""

        if race_id is None:
            return []

        result = await self.db.execute(select(RaceAbilityBonus).where(RaceAbilityBonus.race_id == race_id))
        return list(result.scalars().unique().all())

    async def get_feat_increases(self, character_id: int) -> list[FeatAbilityScoreIncrease]:
        """Fetch the ASI choices granted to a character via their feat grants."""

        result = await self.db.execute(
            select(FeatAbilityScoreIncrease)
            .join(CharacterFeat, CharacterFeat.ability_score_increase_id == FeatAbilityScoreIncrease.id)
            .where(CharacterFeat.character_id == character_id)
            .options(selectinload(FeatAbilityScoreIncrease.feat))
        )
        return list(result.scalars().unique().all())

    async def upsert(self, character_id: int, totals: dict) -> CharacterAbilityScore:
        """
        Create or update the cached effective ability scores for a
        character. ``totals`` keys are ``strength_total``,
        ``dexterity_total``, ``constitution_total``,
        ``intelligence_total``, ``wisdom_total``, ``charisma_total``.
        """

        cache = await self.get_by_character_id(character_id)
        if cache is None:
            cache = CharacterAbilityScore(character_id=character_id, **totals)
            self.db.add(cache)
        else:
            for field, value in totals.items():
                setattr(cache, field, value)

        await self.db.commit()
        await self.db.refresh(cache)

        return cache

    async def get_classes(self, class_ids: list[int]) -> dict[int, Class]:
        """Return ``{id: Class}`` for the given class ids (missing ids are absent)."""

        if not class_ids:
            return {}

        result = await self.db.execute(select(Class).where(Class.id.in_(class_ids)))
        return {row.id: row for row in result.scalars().unique().all()}

    async def get_races(self, race_ids: list[int]) -> dict[int, Race]:
        """Return ``{id: Race}`` for the given race ids (missing ids are absent)."""

        if not race_ids:
            return {}

        result = await self.db.execute(select(Race).where(Race.id.in_(race_ids)))
        return {row.id: row for row in result.scalars().unique().all()}

    async def get_armor_by_character_ids(self, character_ids: list[int]) -> dict[int, list[ArmorSpec]]:
        """
        Return ``{character_id: [ArmorSpec, ...]}`` for the characters' *equipped*
        armor items, ordered by stack id.

        Only items typed ``ARMOR`` with an ``armor_class_base`` count; a
        character with several equipped armor stacks is a misconfiguration, so
        callers use the first spec deterministically.
        """

        if not character_ids:
            return {}

        result = await self.db.execute(
            select(CharacterItem)
            .options(joinedload(CharacterItem.item))
            .join(Item, CharacterItem.item_id == Item.id)
            .where(
                CharacterItem.character_id.in_(character_ids),
                CharacterItem.is_equipped.is_(True),
                Item.item_type == ItemType.ARMOR,
                Item.armor_class_base.is_not(None),
            )
            .order_by(CharacterItem.id)
        )
        rows = list(result.scalars().unique().all())

        result_dict: dict[int, list[ArmorSpec]] = {}
        for row in rows:
            result_dict.setdefault(row.character_id, []).append(
                ArmorSpec(
                    base=row.item.armor_class_base,
                    dex_bonus=row.item.armor_class_dex_bonus,
                    max_dex_bonus=row.item.armor_class_max_dex_bonus,
                )
            )

        return result_dict
