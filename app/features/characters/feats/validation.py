"""Validation helpers for feat-ASI operations on a character (GM grants and level-up)."""

from app.constants import ABILITY_SCORE_CAP
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.feats.exceptions import (
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException
from app.features.feats.crud.repository import feat_ability_score_effects
from app.models.character_model import Character
from app.models.feature_model import Feature


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
    A feat offering ability-score increase options MUST be taken with an
    explicit choice, so its points are never silently lost.
    """

    increases = feat_ability_score_effects(feat)
    if ability_score_increase_id is None and increases:
        raise FeatAsiChoiceRequiredException(feat_id=feat.id, choices=len(increases))


async def validate_ability_score_increase_cap(
    feat: Feature, ability_score_increase_id: int, character: Character, stats_service: CharacterStatsService
) -> None:
    """
    Raise ``AbilityScoreCapExceededException`` if the selected ASI choice
    would push the character's effective score above ``ABILITY_SCORE_CAP``
    (20). Player structured choices (ASI or feat) are always bounded by 20 —
    only GM-panel adjustments or feature effects may go above. The check
    validates against effective totals computed fresh, not the cache.
    """

    increase = next((e for e in feat_ability_score_effects(feat) if e.id == ability_score_increase_id), None)
    if increase is None:
        return

    totals = await stats_service.compute(character)
    total_field = TOTAL_FIELD_BY_ABILITY[increase.ability]
    current_total = totals[total_field]
    requested = current_total + increase.amount

    if requested > ABILITY_SCORE_CAP:
        raise AbilityScoreCapExceededException(
            ability=increase.ability.value,
            current_total=current_total,
            requested=requested,
        )


async def check_feat_prerequisite(character: Character, feat: Feature, stats_service: CharacterStatsService) -> None:
    """
    Raise ``FeatPrerequisiteNotMetException`` if the feat has an
    ability-score prerequisite the character's current *effective* score
    doesn't meet (computed fresh, not from the cache).
    """

    if feat.prerequisite_ability is None or feat.prerequisite_minimum_score is None:
        return

    totals = await stats_service.compute(character)
    field = TOTAL_FIELD_BY_ABILITY[feat.prerequisite_ability]
    actual = totals[field]

    if actual < feat.prerequisite_minimum_score:
        raise FeatPrerequisiteNotMetException(
            feat_id=feat.id,
            ability=feat.prerequisite_ability.value,
            required_minimum=feat.prerequisite_minimum_score,
            actual=actual,
        )
