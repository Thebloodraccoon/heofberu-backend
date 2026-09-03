"""Pure calculation of a character's effective ability scores and derived combat stats (no DB access)."""

from dataclasses import dataclass

from app.constants import ABILITY_SCORE_CAP, MAX_ABILITY_SCORE_CAP, AbilityScore
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
    Computes a character's effective ability scores: the base value plus
    race/subrace bonuses, feat-granted increases, counted ASI-log
    increases, and feature increases. Pure — bonus rows are loaded by the
    caller and passed in.
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
        Return ``{"strength_total": int, ..., "charisma_total": int}``
        for the character, ready for ``CharacterStatsRepository.upsert``.
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
    Resolve each ability's maximum: the standard 20, raised by any
    granted feature's ``new_cap`` (never above the hard ceiling). Pure.
    """

    caps = dict.fromkeys(AbilityScore, ABILITY_SCORE_CAP)
    for increase in feature_increases:
        if increase.new_cap is not None:
            caps[increase.ability] = min(MAX_ABILITY_SCORE_CAP, max(caps[increase.ability], increase.new_cap))
    return caps


# Walk speed used when a character has no race assigned (matches the
# ``Race.speed`` default and the standard 5e default of 30 ft).
DEFAULT_SPEED = 30


@dataclass(frozen=True)
class DerivedStats:
    """A character's derived combat stats, ready to be exposed in a response."""

    hit_dice: str
    speed: int


@dataclass(frozen=True)
class StatContribution:
    """
    One source's contribution to an ability's effective total — the
    machine-readable ``source`` kind, a human-readable ``label``, and the
    signed ``amount`` it added.
    """

    source: str
    label: str
    amount: int


@dataclass(frozen=True)
class AbilityBreakdown:
    """A single ability's score breakdown: the ORIGINAL base value, its COMPUTED total, and the contributions that produced it."""

    base: int
    total: int
    contributions: list[StatContribution]
