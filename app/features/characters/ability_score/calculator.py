"""Pure calculation of a character's effective ability scores."""

from app.constants import AbilityScore
from app.models.character_model import Character
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus

BASE_FIELD_BY_ABILITY = {
    AbilityScore.STR: "strength",
    AbilityScore.DEX: "dexterity",
    AbilityScore.CON: "constitution",
    AbilityScore.INT: "intelligence",
    AbilityScore.WIS: "wisdom",
    AbilityScore.CHA: "charisma",
}

TOTAL_FIELD_BY_ABILITY = {
    AbilityScore.STR: "strength_total",
    AbilityScore.DEX: "dexterity_total",
    AbilityScore.CON: "constitution_total",
    AbilityScore.INT: "intelligence_total",
    AbilityScore.WIS: "wisdom_total",
    AbilityScore.CHA: "charisma_total",
}


class CharacterAbilityScoreCalculator:
    """
    Computes a character's effective ability scores: base value
    (``Character.strength`` etc, what the player entered) plus every
    applicable bonus.

    Bonus sources considered:
      - ``race.ability_bonuses`` (RaceAbilityBonus rows for the
        character's race, if any);
      - feat-granted ability score increases: for each row in
        ``character_feats``, if ``ability_score_increase_id`` is set,
        the corresponding ``FeatAbilityScoreIncrease.amount`` is added
        for that ability.

    Background bonuses are not modeled in the current schema (Background
    has no ability-bonus association table), so they're intentionally
    not included here — add a source here if/when that changes.

    This is a PURE calculation helper — it does not touch the database
    or the ``character_ability_scores`` cache table. The bonus rows
    (``race_bonuses``/``feat_increases``) are loaded by the caller and
    passed in (see ``CharacterAbilityScoreCacheRepository.get_race_bonuses``
    / ``get_feat_increases``, or the ``CharacterAbilityCacheService.compute``
    convenience), which makes this class directly unit-testable with zero
    DB setup — the old version took a ``Session`` and ran the queries
    itself.
    """

    def compute(
        self,
        character: Character,
        race_bonuses: list[RaceAbilityBonus],
        feat_increases: list[FeatAbilityScoreIncrease],
    ) -> dict[str, int]:
        """
        Return a dict of ``{"strength_total": int, ..., "charisma_total": int}``
        for the given character, ready to pass to
        ``CharacterAbilityScoreCacheRepository.upsert``.
        """

        totals = {ability: getattr(character, BASE_FIELD_BY_ABILITY[ability]) for ability in AbilityScore}

        for bonus in race_bonuses:
            totals[bonus.ability] = totals.get(bonus.ability, 0) + bonus.bonus

        for increase in feat_increases:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        return {TOTAL_FIELD_BY_ABILITY[ability]: value for ability, value in totals.items()}
