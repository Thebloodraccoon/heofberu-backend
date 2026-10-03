"""Character stats service: the ability-score cache and derived stats."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import (
    AbilityBreakdown,
    CharacterAbilityScoreCalculator,
    DerivedStats,
)
from app.features.characters.ability_score.repository import CharacterStatsRepository
from app.models import Character, CharacterAbilityScore


@dataclass(frozen=True)
class _Sources:
    """Calculator source rows grouped by race / subrace / character id."""

    race_bonuses: dict
    subrace_bonuses: dict
    asi: dict
    features: dict


class CharacterStatsService:
    """
    Single point that decides when the effective-ability-score cache needs
    recomputing, and the only place that writes ``character_ability_scores``.
    Also provides the derived stats (hit dice).
    """

    def __init__(self, db: AsyncSession):
        """Create the calculator and the stats repository."""

        self.calculator = CharacterAbilityScoreCalculator()
        self.repository = CharacterStatsRepository(db)

    async def compute(self, character: Character) -> dict[str, int]:
        """
        Recompute a character's effective ability scores WITHOUT writing
        to the cache table — fresh data even if the cache is stale.
        """

        return (await self.compute_many([character]))[character.id]

    async def compute_many(self, characters: list[Character]) -> dict[int, dict[str, int]]:
        """
        Batched :meth:`compute`: four queries for the whole list (race/subrace
        bonuses by distinct id, ASI/feature increases by character id) —
        used when one write affects many characters (a GM feature/bonus edit).
        """

        sources = await self._load_sources(characters)
        return {
            character.id: self.calculator.compute(
                character,
                sources.race_bonuses.get(character.race_id, []),
                sources.subrace_bonuses.get(character.subrace_id, []),
                sources.asi.get(character.id, []),
                sources.features.get(character.id, []),
            )
            for character in characters
        }

    async def compute_breakdown(self, character: Character) -> dict[AbilityScore, AbilityBreakdown]:
        """
        Each ability's ORIGINAL base, COMPUTED total, and the labeled
        ``StatContribution`` sources that produced it (read-only).
        """

        sources = await self._load_sources([character])
        race_names = await self.repository.get_race_names([character.race_id] if character.race_id else [])
        subrace_names = await self.repository.get_subrace_names([character.subrace_id] if character.subrace_id else [])

        race_id, subrace_id = character.race_id, character.subrace_id
        return self.calculator.breakdown(
            character,
            sources.race_bonuses.get(race_id, []) if race_id is not None else [],
            sources.subrace_bonuses.get(subrace_id, []) if subrace_id is not None else [],
            sources.asi.get(character.id, []),
            sources.features.get(character.id, []),
            race_name=race_names.get(race_id) if race_id is not None else None,
            subrace_name=subrace_names.get(subrace_id) if subrace_id is not None else None,
        )

    async def refresh(self, character: Character, *, commit: bool = True) -> CharacterAbilityScore:
        """Recompute effective ability scores for ``character`` and persist them."""

        return await self.store(character, await self.compute(character), commit=commit)

    async def store(
        self, character: Character, totals: dict[str, int], *, commit: bool = True
    ) -> CharacterAbilityScore:
        """Persist already computed ``totals`` as the character's ability-score cache row (no recomputation)."""

        return await self.repository.upsert(character.id, totals, commit=commit)

    async def refresh_many(
        self, characters: list[Character], *, commit: bool = True
    ) -> dict[int, CharacterAbilityScore]:
        """Batched :meth:`refresh` — see :meth:`compute_many`."""

        if not characters:
            return {}

        totals_by_character = await self.compute_many(characters)
        return await self.repository.upsert_many(totals_by_character, commit=commit)

    async def get_or_stale(self, character_id: int) -> CharacterAbilityScore | None:
        """The existing cache row as-is, or ``None`` if it was never computed."""

        return await self.repository.get_by_character_id(character_id)

    async def get_many_or_stale(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """Existing cache rows for many characters in one query, keyed by ``character_id`` (missing rows absent)."""

        return await self.repository.get_many_by_character_ids(character_ids)

    async def compute_derived(self, character: Character) -> DerivedStats:
        """Derived stats of one character (see :meth:`get_many_derived`)."""

        return (await self.get_many_derived([character]))[character.id]

    async def get_many_derived(self, characters: list[Character]) -> dict[int, DerivedStats]:
        """``{character_id: DerivedStats}`` — hit dice from the class (one two-column query)."""

        hit_dice = await self.repository.get_hit_dice(
            [character.class_id for character in characters if character.class_id is not None]
        )
        return {character.id: DerivedStats(hit_dice=hit_dice.get(character.class_id, "")) for character in characters}

    async def _load_sources(self, characters: list[Character]) -> _Sources:
        """Load every source row the calculator needs for ``characters`` (four batched queries)."""

        character_ids = [character.id for character in characters]
        return _Sources(
            race_bonuses=await self.repository.get_race_bonuses_many([c.race_id for c in characters]),
            subrace_bonuses=await self.repository.get_subrace_bonuses_many([c.subrace_id for c in characters]),
            asi=await self.repository.get_asi_increases_many(character_ids),
            features=await self.repository.get_feature_increases_many(character_ids),
        )
