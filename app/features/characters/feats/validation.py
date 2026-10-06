"""
Validation helpers for feat-ASI operations on a character (GM grants and level-up).

The ``ensure_*`` functions are pure (they take already computed ability
``totals``); the ``async`` wrappers compute fresh totals for callers that have
none to hand.
"""

from app.constants import ABILITY_SCORE_CAP, AbilityScore
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.feats.exceptions import (
    AbilityScoreCapExceededException,
    FeatAsiChoiceRequiredException,
    FeatMinLevelNotMetException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.feats.crud.repository import feat_ability_score_effects
from app.models.character.character_model import Character
from app.models.features.feature_model import Feature


def validate_ability_score_increase(feat: Feature, ability_score_increase_id: int | None) -> None:
    """
    Raise ``InvalidAbilityScoreIncreaseException`` unless the id is one of
    ``feat``'s own ability-score-effect alternatives. A ``None`` value is
    silently accepted (the caller is responsible for requiring a choice).
    """

    if ability_score_increase_id is None:
        return
    valid_ids = {effect.id for effect in feat_ability_score_effects(feat)}
    if ability_score_increase_id not in valid_ids:
        raise InvalidAbilityScoreIncreaseException(feat_id=feat.id, ability_score_increase_id=ability_score_increase_id)


def validate_asi_choice_required(feat: Feature, ability_score_increase_id: int | None) -> None:
    """
    Raise unless an ASI-offering feat is given an explicit choice.

    Enforced by ``GmPanelFeatService.update_feat`` (an already-granted feat's
    ASI choice must always resolve to one of its options, never back to
    unset) and by a rebuild (which has no later step to answer the pick). A
    fresh GM grant (``add_feat``) does NOT call this — it may leave the
    choice group pending, like any other feature choice group.
    """

    increases = feat_ability_score_effects(feat)
    if ability_score_increase_id is None and increases:
        raise FeatAsiChoiceRequiredException(feat_id=feat.id, choices=len(increases))


def ensure_within_cap(totals: dict[str, int], ability: AbilityScore, amount: int) -> None:
    """Raise ``AbilityScoreCapExceededException`` if ``amount`` on top of the effective total passes ``ABILITY_SCORE_CAP``."""

    current_total = totals[TOTAL_FIELD_BY_ABILITY[ability]]
    requested = current_total + amount
    if requested > ABILITY_SCORE_CAP:
        raise AbilityScoreCapExceededException(ability=ability.value, current_total=current_total, requested=requested)


def ensure_feat_asi_within_cap(feat: Feature, ability_score_increase_id: int | None, totals: dict[str, int]) -> None:
    """
    Raise ``AbilityScoreCapExceededException`` if the feat's selected ASI
    option would push the effective score above ``ABILITY_SCORE_CAP`` (20).
    Player structured choices (ASI or feat) are always bounded by 20 — only
    GM-panel adjustments or feature effects may go above.
    """

    increase = next((e for e in feat_ability_score_effects(feat) if e.id == ability_score_increase_id), None)
    if increase is not None:
        ensure_within_cap(totals, increase.ability, increase.amount)


def ensure_prerequisite_met(feat: Feature, totals: dict[str, int]) -> None:
    """Raise ``FeatPrerequisiteNotMetException`` if the feat's ability-score prerequisite is unmet by ``totals``."""

    if feat.prerequisite_ability is None or feat.prerequisite_minimum_score is None:
        return

    actual = totals[TOTAL_FIELD_BY_ABILITY[feat.prerequisite_ability]]
    if actual < feat.prerequisite_minimum_score:
        raise FeatPrerequisiteNotMetException(
            feat_id=feat.id,
            ability=feat.prerequisite_ability.value,
            required_minimum=feat.prerequisite_minimum_score,
            actual=actual,
        )


async def check_feat_prerequisite(character: Character, feat: Feature, stats_service: CharacterStatsService) -> None:
    """:func:`ensure_prerequisite_met` against the character's *effective* score (computed fresh, not the cache)."""

    if feat.prerequisite_ability is None or feat.prerequisite_minimum_score is None:
        return

    ensure_prerequisite_met(feat, await stats_service.compute(character))


def ensure_feat_min_level(feat: Feature, level: int) -> None:
    """Raise ``FeatMinLevelNotMetException`` if the feat has a ``min_level`` above the level it is taken at."""

    if feat.min_level is not None and level < feat.min_level:
        raise FeatMinLevelNotMetException(feat_id=feat.id, min_level=feat.min_level, level=level)
