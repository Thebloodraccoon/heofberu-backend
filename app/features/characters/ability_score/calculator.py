"""Pure calculation of a character's effective ability scores and derived combat stats (no DB access)."""

from dataclasses import dataclass

from app.constants import ABILITY_SCORE_CAP, MAX_ABILITY_SCORE_CAP, AbilityScore
from app.models.character.character_model import Character
from app.models.races.race_association_models import RaceAbilityBonus
from app.models.races.subrace_association_models import SubraceAbilityBonus

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


DEFAULT_SPEED = 30
"""Walk speed (ft) for a character without a race; matches the ``Race.speed`` default."""


@dataclass(frozen=True)
class DerivedStats:
    """A character's derived stats exposed in a response: hit dice come from the class on every read."""

    hit_dice: str


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


class CharacterAbilityScoreCalculator:
    """
    Computes a character's effective ability scores: the base value plus
    race/subrace bonuses, counted ASI-log increases, and feature
    increases. Pure — bonus rows are loaded by the caller and passed in.
    """

    def compute(
        self,
        character: Character,
        race_bonuses: list[RaceAbilityBonus],
        subrace_bonuses: list[SubraceAbilityBonus],
        asi_increases: list | None = None,
        feature_increases: list | None = None,
    ) -> dict[str, int]:
        """
        Return ``{"strength_total": int, ..., "charisma_total": int}``
        for the character, ready for ``CharacterStatsRepository.upsert``.
        Totals are floored at 1 (the 5e minimum) however many negative
        bonuses stack up.
        """

        totals = {ability: getattr(character, BASE_FIELD_BY_ABILITY[ability]) for ability in AbilityScore}

        for bonus in race_bonuses:
            totals[bonus.ability] = totals.get(bonus.ability, 0) + bonus.bonus

        for subrace_bonus in subrace_bonuses:
            totals[subrace_bonus.ability] = totals.get(subrace_bonus.ability, 0) + subrace_bonus.bonus

        for increase in asi_increases or []:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        for increase in feature_increases or []:
            totals[increase.ability] = totals.get(increase.ability, 0) + increase.amount

        return {TOTAL_FIELD_BY_ABILITY[ability]: max(1, value) for ability, value in totals.items()}

    def breakdown(
        self,
        character: Character,
        race_bonuses: list[RaceAbilityBonus],
        subrace_bonuses: list[SubraceAbilityBonus],
        asi_increases: list,
        feature_increases: list,
        *,
        race_name: str | None = None,
        subrace_name: str | None = None,
    ) -> dict[AbilityScore, AbilityBreakdown]:
        """
        Per ability: the ORIGINAL base, the COMPUTED total, and the labeled
        contributions (race, subrace, ASI log, features) that produced it.
        """

        totals = self.compute(character, race_bonuses, subrace_bonuses, asi_increases, feature_increases)
        contributions: dict[AbilityScore, list[StatContribution]] = {ability: [] for ability in AbilityScore}

        for bonus in race_bonuses:
            contributions[bonus.ability].append(StatContribution("race", race_name or "Race bonus", bonus.bonus))
        for subrace_bonus in subrace_bonuses:
            contributions[subrace_bonus.ability].append(
                StatContribution("subrace", subrace_name or "Subrace bonus", subrace_bonus.bonus)
            )
        for increase in asi_increases:
            contributions[increase.ability].append(StatContribution("asi", _asi_label(increase), increase.amount))
        for increase in feature_increases:
            contributions[increase.ability].append(
                StatContribution("feature", effect_source_label(increase), increase.amount)
            )

        return {
            ability: AbilityBreakdown(
                base=getattr(character, BASE_FIELD_BY_ABILITY[ability]),
                total=totals[TOTAL_FIELD_BY_ABILITY[ability]],
                contributions=contributions[ability],
            )
            for ability in AbilityScore
        }


def effect_source_label(effect) -> str:
    """
    The feature-name label of an ability effect: the fixed row's ``feature``,
    or the chosen option's owning feature for an option-effect row.
    """

    feature = getattr(effect, "feature", None)
    if feature is None:
        group = getattr(getattr(effect, "choice_option", None), "group", None)
        feature = getattr(group, "feature", None)

    return feature.name if feature is not None and feature.name else "Feature"


def _asi_label(increase) -> str:
    """Label of an ASI-log increment: the class level and choice kind, or a GM adjustment."""

    choice = increase.choice
    if choice is None or choice.class_level is None:
        return "GM adjustment"

    choice_kind = getattr(choice.choice_type, "value", choice.choice_type)
    return f"Level {choice.class_level} ({choice_kind})"


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
