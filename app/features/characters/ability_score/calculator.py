"""
Pure calculation of a character's effective ability scores and derived combat stats.

Effective ability scores are the base values (what the player entered,
never mutated after creation) plus race/subrace bonuses, feat-granted
increases, and the counted ASI-choice log increases; the remaining
derived combat stats (hit dice, speed) are read from the class and race.
Armor class is NOT computed here (or anywhere else) — it's a plain
editable ``Character.armor_class`` column. Both helpers are pure — no
database access.
"""

from dataclasses import dataclass

from app.constants import ABILITY_SCORE_CAP, AbilityScore
from app.models.character_model import Character
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus
from app.models.subrace_association_models import SubraceAbilityBonus

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
      - ``subrace.ability_bonuses`` (SubraceAbilityBonus rows for the
        character's subrace, if any);
      - feat-granted ability score increases: for each row in
        ``character_feats``, if ``ability_score_increase_id`` is set,
        the corresponding ``FeatAbilityScoreIncrease.amount`` is added
        for that ability;
      - ASI-choice log increases (``CharacterASIChoiceIncrease`` rows of
        choices with ``applied_to_base == False``): level-up Ability
        Score Improvements and GM ±adjustments no longer touch the base
        columns — their points live in the audit log and are counted
        here. Legacy rows (``applied_to_base == True``) whose points
        were folded into the base columns are excluded by the loader;
      - feature ability increases (``FeatureAbilityIncrease`` rows of
        features granted to the character via ``character_features``):
        fixed, choice-free effects such as Primal Champion's +4 STR/CON.
        Their optional ``new_cap`` raises that ability's maximum above
        the standard 20 (see ``CharacterStatsService.resolve_ability_caps``).

    Background bonuses are not modeled in the current schema (Background
    has no ability-bonus association table), so they're intentionally
    not included here — add a source here if/when that changes.

    This is a PURE calculation helper — it does not touch the database
    or the ``character_ability_scores`` cache table. The bonus rows
    (``race_bonuses``/``subrace_bonuses``/``feat_increases``/
    ``asi_increases``/``feature_increases``) are loaded by the caller and
    passed in (see
    ``CharacterStatsRepository.get_race_bonuses`` /
    ``get_subrace_bonuses`` / ``get_feat_increases`` /
    ``get_asi_increases`` / ``get_feature_increases``, or the
    ``CharacterStatsService.compute``
    convenience), which makes this class directly unit-testable with
    zero DB setup — the old version took a ``Session`` and ran the
    queries itself.
    """

    def compute(
        self,
        character: Character,
        race_bonuses: list[RaceAbilityBonus],
        subrace_bonuses: list[SubraceAbilityBonus],
        feat_increases: list[FeatAbilityScoreIncrease],
        asi_increases: list | None = None,
        feature_increases: list | None = None,
    ) -> dict[str, int]:
        """
        Return a dict of ``{"strength_total": int, ..., "charisma_total": int}``
        for the given character, ready to pass to
        ``CharacterStatsRepository.upsert``.

        Every bonus argument is a list of objects exposing ``.ability``
        and ``.amount``.
        """

        totals = {ability: getattr(character, BASE_FIELD_BY_ABILITY[ability]) for ability in AbilityScore}

        for bonus in race_bonuses:
            totals[bonus.ability] = totals.get(bonus.ability, 0) + bonus.bonus

        for bonus in subrace_bonuses:
            totals[bonus.ability] = totals.get(bonus.ability, 0) + bonus.bonus

        for increase in feat_increases:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        for increase in asi_increases or []:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        for increase in feature_increases or []:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        # Effective scores never drop below 1 (the 5e minimum), no matter
        # how many negative bonuses stack up (e.g. cursed features).
        return {TOTAL_FIELD_BY_ABILITY[ability]: max(1, value) for ability, value in totals.items()}


def resolve_ability_caps(feature_increases: list) -> dict[AbilityScore, int]:
    """
    Resolve each ability's maximum score: the standard
    ``ABILITY_SCORE_CAP`` (20), raised to ``max(cap, new_cap)`` by every
    granted feature effect that carries a ``new_cap`` (e.g. Primal
    Champion lifts STR/CON to 24). Pure — no database access.
    """

    caps = dict.fromkeys(AbilityScore, ABILITY_SCORE_CAP)
    for increase in feature_increases:
        if increase.new_cap is not None:
            caps[increase.ability] = max(caps[increase.ability], increase.new_cap)
    return caps


# Walk speed used when a character has no race assigned (matches the
# ``Race.speed`` default and the standard 5e default of 30 ft).
DEFAULT_SPEED = 30


@dataclass(frozen=True)
class DerivedStats:
    """A character's derived combat stats, ready to be exposed in a response."""

    hit_dice: str
    speed: int
