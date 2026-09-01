"""Repository for a character's effective ability scores and derived combat stats."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import (
    CharacterAbilityScore,
    Class,
    Race,
    Subrace,
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
    Repository backing ``CharacterStatsService``: the
    ``character_ability_scores`` cache table plus the source-bonus and
    reference-data queries the calculator and derived stats need.
    """

    def __init__(self, db: AsyncSession):
        """Create the stats repository."""

        super().__init__(CharacterAbilityScore, db)

    async def get_by_character_id(self, character_id: int) -> CharacterAbilityScore | None:
        """Fetch the cached effective-ability-score row, or None if never computed."""

        result = await self.db.execute(
            select(CharacterAbilityScore).where(CharacterAbilityScore.character_id == character_id)
        )
        return result.scalar_one_or_none()

    async def get_many_by_character_ids(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """
        Fetch the cache rows for many characters in one query, keyed by
        ``character_id`` (kills the old per-row N+1 on listing).
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
        Fetch the counted increments of the character's ASI-choice log
        (choices with ``applied_to_base == False``). Legacy pre-rework
        choices are excluded so their points don't apply twice.
        """

        result = await self.db.execute(
            select(CharacterASIChoiceIncrease)
            .join(CharacterASIChoice, CharacterASIChoice.id == CharacterASIChoiceIncrease.character_asi_choice_id)
            .where(
                CharacterASIChoice.character_id == character_id,
                CharacterASIChoice.applied_to_base.is_(False),
            )
            .options(selectinload(CharacterASIChoiceIncrease.choice))
        )
        return list(result.scalars().all())

    async def get_feature_increases(self, character_id: int) -> list[FeatureAbilityIncrease]:
        """
        Fetch the fixed ability-score effects of every feature granted to
        the character — e.g. Primal Champion's +4 STR/CON. They apply
        automatically while the grant exists.
        """

        result = await self.db.execute(
            select(FeatureAbilityIncrease)
            .join(CharacterFeature, CharacterFeature.feature_id == FeatureAbilityIncrease.feature_id)
            .where(CharacterFeature.character_id == character_id)
            .options(selectinload(FeatureAbilityIncrease.feature))
        )
        return list(result.scalars().all())

    async def upsert(self, character_id: int, totals: dict, *, commit: bool = True) -> CharacterAbilityScore:
        """
        Create or update the cached effective ability scores for a
        character, keyed by ``strength_total`` .. ``charisma_total``.
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

    async def get_subraces(self, subrace_ids: list[int]) -> dict[int, Subrace]:
        """Return ``{id: Subrace}`` for the given subrace ids (missing ids are absent)."""

        if not subrace_ids:
            return {}

        result = await self.db.execute(select(Subrace).where(Subrace.id.in_(subrace_ids)))
        return {row.id: row for row in result.scalars().unique().all()}
