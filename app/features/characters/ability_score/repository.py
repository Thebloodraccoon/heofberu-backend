"""Repository for a character's effective ability scores and derived combat stats."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import (
    CharacterAbilityScore,
    Class,
    Race,
)
from app.models.character_asi_choice_model import CharacterASIChoice, CharacterASIChoiceIncrease
from app.models.character_association_models import CharacterFeat
from app.models.character_feature_model import CharacterFeature
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.feature_model import FeatureAbilityIncrease
from app.models.race_association_models import RaceAbilityBonus
from app.models.subrace_association_models import SubraceAbilityBonus


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

    The derived combat stats (hit dice, speed) load their references
    (class, race) through the same batch queries, so a listing page costs
    a constant number of queries.
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

    async def get_subrace_bonuses(self, subrace_id: int | None) -> list[SubraceAbilityBonus]:
        """Fetch a subrace's ability bonuses, or ``[]`` for a character with no subrace."""

        if subrace_id is None:
            return []

        result = await self.db.execute(select(SubraceAbilityBonus).where(SubraceAbilityBonus.subrace_id == subrace_id))
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

    async def get_asi_increases(self, character_id: int) -> list[CharacterASIChoiceIncrease]:
        """
        Fetch the counted increments of the character's ASI-choice log:
        every ``CharacterASIChoiceIncrease`` whose parent choice has
        ``applied_to_base == False`` (level-up ASIs and GM ±adjustments
        recorded after the log-based rework). Legacy rows — pre-rework
        choices whose points were folded into the base columns — are
        excluded here so their points don't apply twice.
        """

        result = await self.db.execute(
            select(CharacterASIChoiceIncrease)
            .join(CharacterASIChoice, CharacterASIChoice.id == CharacterASIChoiceIncrease.character_asi_choice_id)
            .where(
                CharacterASIChoice.character_id == character_id,
                CharacterASIChoice.applied_to_base.is_(False),
            )
        )
        return list(result.scalars().all())

    async def get_feature_increases(self, character_id: int) -> list[FeatureAbilityIncrease]:
        """
        Fetch the fixed ability-score effects of every feature currently
        granted to the character (``character_features``), e.g. Primal
        Champion's +4 STR/CON rows. Purely automatic — no choice log
        involved; the effect applies exactly while the grant exists.
        """

        result = await self.db.execute(
            select(FeatureAbilityIncrease)
            .join(CharacterFeature, CharacterFeature.feature_id == FeatureAbilityIncrease.feature_id)
            .where(CharacterFeature.character_id == character_id)
        )
        return list(result.scalars().all())

    async def upsert(self, character_id: int, totals: dict, *, commit: bool = True) -> CharacterAbilityScore:
        """
        Create or update the cached effective ability scores for a
        character. ``totals`` keys are ``strength_total``,
        ``dexterity_total``, ``constitution_total``,
        ``intelligence_total``, ``wisdom_total``, ``charisma_total``.

        ``commit=False`` flushes instead — for bulk refreshes running
        inside a caller's transaction (e.g. source reconciliation).
        """

        cache = await self.get_by_character_id(character_id)
        if cache is None:
            cache = CharacterAbilityScore(character_id=character_id, **totals)
            self.db.add(cache)
        else:
            for field, value in totals.items():
                setattr(cache, field, value)

        if commit:
            await self.db.commit()
            await self.db.refresh(cache)
        else:
            await self.db.flush()

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
