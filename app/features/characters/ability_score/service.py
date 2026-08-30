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
    Single point of decision for "when does the effective-ability-score
    cache need recomputing", and the only place that writes to
    ``character_ability_scores``.

    Before this existed, three call sites each decided independently
    when to recalculate: ``CharacterService._to_response`` (via
    ``_ABILITY_AFFECTING_FIELDS``), the feat-grant writes (always,
    on every feat write), and race changes (indirectly, via the same
    field set). Consolidating them here means a new ability-affecting
    change (e.g. a future background bonus source) only needs to be
    wired into this one class, not hunted down across every sub-service.

    Entry points:
      - ``compute`` — recompute a character's effective scores from the
        current source rows WITHOUT persisting (read-only use, e.g. the
        feat-prerequisite check in ``characters.feats.validation``, or the
        progression service's ASI cap / hit-point modifier checks).
      - ``refresh`` — ``compute`` + persist. Used by every write path
        that's already known to affect ability scores (feat
        grant/update/remove; character create; race change; level-up
        ASI, via ``CharacterProgressionService``).
      - ``get_or_stale`` — read the existing cache row without
        recomputing. Used by list views that intentionally trade
        freshness for avoiding N recalculations per page.
      - ``get_many_or_stale`` — same as ``get_or_stale`` but for a whole
        listing page in one query (kills the N+1 in
        ``CharacterService.get_characters``).
      - ``for_response`` — thin dispatcher used by
        ``CharacterService._to_response``: ``refresh`` when ``refresh``
        is ``True``, else ``get_or_stale``.

    This service is also the home of the remaining derived combat stats
    that a ``CharacterResponse`` exposes instead of class/race lookups on
    every consumer:
      - ``compute_derived`` — for a single character;
      - ``get_many_derived`` — for a listing page, so a page costs a
        constant number of queries regardless of page size.

    Because these are derived on every read, no write path needs to keep
    them in sync, and a GM editing a class's hit die or a race's speed
    shows up the next time the character is fetched. Armor class is NOT
    derived here (or anywhere) — it's a plain editable
    ``Character.armor_class`` column.
    """

    def __init__(self, db: AsyncSession):
        self.calculator = CharacterAbilityScoreCalculator()
        self.repository = CharacterStatsRepository(db)

    async def compute(self, character: Character) -> dict[str, int]:
        """
        Recompute a character's effective ability scores WITHOUT writing
        to the cache table.

        Loads the source bonus rows (race + subrace bonuses + feat ASI
        choices + counted ASI-choice log increases) and feeds them to
        the pure :class:`CharacterAbilityScoreCalculator`. Used by
        read-only callers that need "what would the current scores be" —
        e.g. the feat prerequisite check, which must be based on fresh
        data even if the cache is stale.
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
        Compute each ability's ORIGINAL base, its COMPUTED total, and the
        list of ``StatContribution`` sources that produced that total —
        the "what is calculated from what" view shown to the player.

        Loads the same source rows as :meth:`compute` (race/subrace
        bonuses + feat ASI + counted ASI-log increases + feature
        increases) and labels them for display (race/subrace/feature/feat
        names, or "Level N (CHOICE)"). Does NOT persist anything — read-only.
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
        subrace_rows = await self.repository.get_subraces([character.subrace_id]) if character.subrace_id is not None else {}
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
            contributions[increase.ability].append(
                StatContribution(source="asi", label=label, amount=increase.amount)
            )
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
        ``new_cap`` (e.g. 24 for STR/CON under Primal Champion). Computed
        fresh from the current feature grants — used by every cap check
        (level-up ASI, GM ±adjustments, feat ASI choices).
        """

        feature_increases = await self.repository.get_feature_increases(character.id)
        return resolve_ability_caps(feature_increases)

    async def refresh(self, character: Character, *, commit: bool = True) -> CharacterAbilityScore:
        """
        Recompute effective ability scores for ``character`` and persist
        them. ``commit=False`` defers persistence to the caller's
        transaction (bulk refreshes inside a source reconciliation).
        """

        totals = await self.compute(character)
        return await self.repository.upsert(character.id, totals, commit=commit)

    async def get_or_stale(self, character_id: int) -> CharacterAbilityScore | None:
        """
        Return the existing cache row as-is, without recomputing.
        ``None`` if the character has never had its scores computed
        (e.g. never fetched individually via ``GET /{character_id}``).
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
        Return ``{character_id: DerivedStats}`` for the given characters.

        Hit dice come from the character's class, speed from its race
        (falling back to the standard 30 ft without one). Armor class is
        not derived — it lives on the ``Character.armor_class`` column.
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
