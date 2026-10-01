"""Repository for a character's effective ability scores and the source rows they are computed from."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import CharacterAbilityScore, Class, Race, Subrace
from app.models.character.character_asi_choice_model import CharacterASIChoice, CharacterASIChoiceIncrease
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_feature_model import CharacterFeature
from app.models.features.feature_engine_models import (
    FeatureAbilityScoreEffect,
    FeatureChoiceGroup,
    FeatureChoiceOption,
)
from app.models.races.race_association_models import RaceAbilityBonus
from app.models.races.subrace_association_models import SubraceAbilityBonus
from app.settings._common import utcnow


class CharacterStatsRepository(BaseRepository[CharacterAbilityScore]):
    """
    Repository backing ``CharacterStatsService``: the
    ``character_ability_scores`` cache table plus the source-bonus and
    reference-data queries the calculator needs. Source lookups are batched
    (one query per source kind for any number of characters).
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
        """Fetch the cache rows for many characters in one query, keyed by ``character_id``."""

        if not character_ids:
            return {}

        result = await self.db.execute(
            select(CharacterAbilityScore).where(CharacterAbilityScore.character_id.in_(character_ids))
        )
        return {row.character_id: row for row in result.scalars().unique().all()}

    async def get_race_bonuses_many(self, race_ids: Iterable[int | None]) -> dict[int, list[RaceAbilityBonus]]:
        """Ability bonuses of every given race, grouped by race id (one query)."""

        ids = {race_id for race_id in race_ids if race_id is not None}
        if not ids:
            return {}

        result = await self.db.execute(select(RaceAbilityBonus).where(RaceAbilityBonus.race_id.in_(ids)))
        grouped: dict[int, list[RaceAbilityBonus]] = {}
        for row in result.scalars().unique().all():
            grouped.setdefault(row.race_id, []).append(row)
        return grouped

    async def get_subrace_bonuses_many(self, subrace_ids: Iterable[int | None]) -> dict[int, list[SubraceAbilityBonus]]:
        """Ability bonuses of every given subrace, grouped by subrace id (one query)."""

        ids = {subrace_id for subrace_id in subrace_ids if subrace_id is not None}
        if not ids:
            return {}

        result = await self.db.execute(select(SubraceAbilityBonus).where(SubraceAbilityBonus.subrace_id.in_(ids)))
        grouped: dict[int, list[SubraceAbilityBonus]] = {}
        for row in result.scalars().unique().all():
            grouped.setdefault(row.subrace_id, []).append(row)
        return grouped

    async def get_asi_increases_many(self, character_ids: list[int]) -> dict[int, list[CharacterASIChoiceIncrease]]:
        """
        Counted increments of the characters' ASI-choice logs (choices with
        ``applied_to_base == False``; legacy pre-rework choices are excluded
        so their points don't apply twice), grouped by character id.
        """

        if not character_ids:
            return {}

        result = await self.db.execute(
            select(CharacterASIChoiceIncrease, CharacterASIChoice.character_id)
            .join(CharacterASIChoice, CharacterASIChoice.id == CharacterASIChoiceIncrease.character_asi_choice_id)
            .where(
                CharacterASIChoice.character_id.in_(character_ids),
                CharacterASIChoice.applied_to_base.is_(False),
            )
            .options(selectinload(CharacterASIChoiceIncrease.choice))
        )
        grouped: dict[int, list[CharacterASIChoiceIncrease]] = {}
        for increase, character_id in result.unique().all():
            grouped.setdefault(character_id, []).append(increase)
        return grouped

    async def get_feature_increases_many(self, character_ids: list[int]) -> dict[int, list]:
        """
        Ability-score effects of every feature granted to the characters
        (e.g. Primal Champion's +4 STR/CON), grouped by character id: the
        fixed effect rows plus the option rows of the picks stored in
        ``character_feature_choices``. Two queries total.
        """

        grouped: dict[int, list] = {character_id: [] for character_id in character_ids}
        if not character_ids:
            return grouped

        fixed_result = await self.db.execute(
            select(FeatureAbilityScoreEffect, CharacterFeature.character_id)
            .join(CharacterFeature, CharacterFeature.feature_id == FeatureAbilityScoreEffect.feature_id)
            .where(
                CharacterFeature.character_id.in_(character_ids),
                FeatureAbilityScoreEffect.feature_id.isnot(None),
            )
            .options(selectinload(FeatureAbilityScoreEffect.feature))
        )
        for effect, character_id in fixed_result.unique().all():
            grouped[character_id].append(effect)

        option_result = await self.db.execute(
            select(FeatureAbilityScoreEffect, CharacterFeature.character_id)
            .join(FeatureChoiceOption, FeatureChoiceOption.id == FeatureAbilityScoreEffect.choice_option_id)
            .join(CharacterFeatureChoice, CharacterFeatureChoice.choice_option_id == FeatureChoiceOption.id)
            .join(CharacterFeature, CharacterFeature.id == CharacterFeatureChoice.character_feature_id)
            .where(
                CharacterFeature.character_id.in_(character_ids),
                FeatureAbilityScoreEffect.choice_option_id.isnot(None),
            )
            .options(
                selectinload(FeatureAbilityScoreEffect.choice_option)
                .selectinload(FeatureChoiceOption.group)
                .selectinload(FeatureChoiceGroup.feature)
            )
        )
        for effect, character_id in option_result.unique().all():
            grouped[character_id].append(effect)

        return grouped

    async def upsert(self, character_id: int, totals: dict, *, commit: bool = True) -> CharacterAbilityScore:
        """Create or update one character's cached totals (see :meth:`upsert_many`)."""

        return (await self.upsert_many({character_id: totals}, commit=commit))[character_id]

    async def upsert_many(
        self, totals_by_character_id: dict[int, dict], *, commit: bool = True
    ) -> dict[int, CharacterAbilityScore]:
        """
        Create or update the cached totals (``strength_total`` ..
        ``charisma_total``) of many characters in one atomic
        ``INSERT ... ON CONFLICT DO UPDATE`` — concurrent refreshes of the
        same character can no longer collide on the primary key. Every
        totals dict must carry the same keys.
        """

        if not totals_by_character_id:
            return {}

        rows = [
            {"character_id": character_id, **totals} for character_id, totals in sorted(totals_by_character_id.items())
        ]
        statement = pg_insert(CharacterAbilityScore).values(rows)
        updates = {field: statement.excluded[field] for field in rows[0] if field != "character_id"}
        statement = statement.on_conflict_do_update(
            index_elements=[CharacterAbilityScore.character_id],
            set_={**updates, "updated_at": utcnow()},
        ).returning(CharacterAbilityScore)

        result = await self.db.execute(statement, execution_options={"populate_existing": True})
        cached = {row.character_id: row for row in result.scalars().all()}
        await self.commit_or_flush(commit=commit)
        return cached

    async def get_hit_dice(self, class_ids: Iterable[int]) -> dict[int, str]:
        """``{class_id: hit die}`` (e.g. ``"D10"``) for the given classes, selecting only those two columns."""

        ids = set(class_ids)
        if not ids:
            return {}

        result = await self.db.execute(select(Class.id, Class.hit_dice).where(Class.id.in_(ids)))
        return {class_id: hit_dice.value for class_id, hit_dice in result.all()}

    async def get_race_names(self, race_ids: Iterable[int]) -> dict[int, str]:
        """``{race_id: name}`` for the given races."""

        ids = set(race_ids)
        if not ids:
            return {}

        result = await self.db.execute(select(Race.id, Race.name).where(Race.id.in_(ids)))
        return dict(result.all())

    async def get_subrace_names(self, subrace_ids: Iterable[int]) -> dict[int, str]:
        """``{subrace_id: name}`` for the given subraces."""

        ids = set(subrace_ids)
        if not ids:
            return {}

        result = await self.db.execute(select(Subrace.id, Subrace.name).where(Subrace.id.in_(ids)))
        return dict(result.all())
