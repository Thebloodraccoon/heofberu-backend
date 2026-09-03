"""Character stats service: the ability-score cache and derived combat stats."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import (
    BASE_FIELD_BY_ABILITY,
    DEFAULT_SPEED,
    TOTAL_FIELD_BY_ABILITY,
    AbilityBreakdown,
    CharacterAbilityScoreCalculator,
    DerivedStats,
    StatContribution,
    resolve_ability_caps,
)
from app.features.characters.ability_score.repository import CharacterStatsRepository
from app.models import Character, CharacterAbilityScore


class CharacterStatsService:
    """
    Single point that decides when the effective-ability-score cache needs
    recomputing, and the only place that writes ``character_ability_scores``.
    Also computes the derived combat stats (hit dice, speed).
    """

    def __init__(self, db: AsyncSession):
        """Create the calculator and the stats repository."""

        self.calculator = CharacterAbilityScoreCalculator()
        self.repository = CharacterStatsRepository(db)

    async def compute(self, character: Character) -> dict[str, int]:
        """
        Recompute a character's effective ability scores WITHOUT writing
        to the cache table — for read-only callers (fresh data even if
        the cache is stale).
        """

        race_bonuses = await self.repository.get_race_bonuses(character.race_id)
        subrace_bonuses = await self.repository.get_subrace_bonuses(character.subrace_id)
        feat_increases = await self.repository.get_feat_increases(character.id)
        asi_increases = await self.repository.get_asi_increases(character.id)
        feature_increases = await self.repository.get_feature_increases(character.id)
        return self.calculator.compute(
            character, race_bonuses, subrace_bonuses, feat_increases, asi_increases, feature_increases
        )

    async def compute_breakdown(self, character: Character) -> dict[AbilityScore, AbilityBreakdown]:
        """
        Compute each ability's ORIGINAL base, COMPUTED total, and the
        labeled ``StatContribution`` sources that produced it (read-only).
        """

        race_bonuses = await self.repository.get_race_bonuses(character.race_id)
        subrace_bonuses = await self.repository.get_subrace_bonuses(character.subrace_id)
        feat_increases = await self.repository.get_feat_increases(character.id)
        asi_increases = await self.repository.get_asi_increases(character.id)
        feature_increases = await self.repository.get_feature_increases(character.id)

        totals = self.calculator.compute(
            character, race_bonuses, subrace_bonuses, feat_increases, asi_increases, feature_increases
        )

        contributions: dict[AbilityScore, list[StatContribution]] = {ability: [] for ability in AbilityScore}

        race_rows = await self.repository.get_races([character.race_id]) if character.race_id is not None else {}
        subrace_rows = (
            await self.repository.get_subraces([character.subrace_id]) if character.subrace_id is not None else {}
        )
        race_name = getattr(race_rows.get(character.race_id), "name", None)
        subrace_name = getattr(subrace_rows.get(character.subrace_id), "name", None)

        for bonus in race_bonuses:
            contributions[bonus.ability].append(
                StatContribution(source="race", label=race_name or "Race bonus", amount=bonus.bonus)
            )
        for bonus in subrace_bonuses:
            contributions[bonus.ability].append(
                StatContribution(source="subrace", label=subrace_name or "Subrace bonus", amount=bonus.bonus)
            )
        for increase in feat_increases:
            contributions[increase.ability].append(
                StatContribution(
                    source="feat",
                    label=increase.feat.name if increase.feat is not None else "Feat",
                    amount=increase.amount,
                )
            )
        for increase in asi_increases:
            choice = increase.choice
            if choice is not None and choice.class_level is not None:
                choice_kind = getattr(choice.choice_type, "value", choice.choice_type)
                label = f"Level {choice.class_level} ({choice_kind})"
            else:
                label = "GM adjustment"
            contributions[increase.ability].append(StatContribution(source="asi", label=label, amount=increase.amount))
        for increase in feature_increases:
            contributions[increase.ability].append(
                StatContribution(
                    source="feature",
                    label=increase.feature.name if increase.feature is not None else "Feature",
                    amount=increase.amount,
                )
            )

        return {
            ability: AbilityBreakdown(
                base=getattr(character, BASE_FIELD_BY_ABILITY[ability]),
                total=totals[TOTAL_FIELD_BY_ABILITY[ability]],
                contributions=contributions[ability],
            )
            for ability in AbilityScore
        }

    async def resolve_ability_caps(self, character: Character) -> dict[AbilityScore, int]:
        """
        Resolve each ability's maximum score for ``character``: the
        standard 20 raised by any granted feature effect carrying a
        ``new_cap``. Computed fresh from the current feature grants.
        """

        feature_increases = await self.repository.get_feature_increases(character.id)
        return resolve_ability_caps(feature_increases)

    async def refresh(self, character: Character, *, commit: bool = True) -> CharacterAbilityScore:
        """Recompute effective ability scores for ``character`` and persist them."""

        totals = await self.compute(character)
        return await self.repository.upsert(character.id, totals, commit=commit)

    async def get_or_stale(self, character_id: int) -> CharacterAbilityScore | None:
        """
        Return the existing cache row as-is, without recomputing, or
        ``None`` if it was never computed.
        """

        return await self.repository.get_by_character_id(character_id)

    async def get_many_or_stale(self, character_ids: list[int]) -> dict[int, CharacterAbilityScore]:
        """
        Return the existing cache rows for many characters in one query,
        keyed by ``character_id``. Characters without a row are simply
        absent from the result — see :meth:`get_or_stale`.
        """

        return await self.repository.get_many_by_character_ids(character_ids)

    async def for_response(self, character: Character, *, refresh: bool = False) -> CharacterAbilityScore | None:
        """
        Return the cache row for serializing a character response:
        freshly recomputed+persisted when ``refresh`` is ``True``,
        otherwise the existing row as-is (or ``None``).
        """

        if refresh:
            return await self.refresh(character)

        return await self.get_or_stale(character.id)

    async def compute_derived(self, character: Character) -> DerivedStats:
        """Compute the derived combat stats for a single character (see :meth:`get_many_derived`)."""

        return (await self.get_many_derived([character]))[character.id]

    async def get_many_derived(self, characters: list[Character]) -> dict[int, DerivedStats]:
        """
        Return ``{character_id: DerivedStats}`` for the given characters:
        hit dice from the class, speed from the race (30 ft default).
        """

        class_ids = [character.class_id for character in characters if character.class_id is not None]
        race_ids = [character.race_id for character in characters if character.race_id is not None]

        classes = await self.repository.get_classes(class_ids)
        races = await self.repository.get_races(race_ids)

        result: dict[int, DerivedStats] = {}
        for character in characters:
            character_class = classes.get(character.class_id) if character.class_id is not None else None
            race = races.get(character.race_id) if character.race_id is not None else None

            result[character.id] = DerivedStats(
                hit_dice=character_class.hit_dice.value if character_class is not None else "",
                speed=race.speed if race is not None else DEFAULT_SPEED,
            )
        return result
