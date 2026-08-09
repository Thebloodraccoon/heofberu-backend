"""Shared validation helpers for granting feats to a character."""

from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.feats.exceptions import (
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.models.character_model import Character
from app.models.feat_model import Feat


def validate_ability_score_increase(feat: Feat, ability_score_increase_id: int) -> None:
    """
    Raise ``InvalidAbilityScoreIncreaseException`` unless
    ``ability_score_increase_id`` is one of ``feat``'s own
    ``ability_score_increases`` rows.
    """

    valid_ids = {increase.id for increase in feat.ability_score_increases}
    if ability_score_increase_id not in valid_ids:
        raise InvalidAbilityScoreIncreaseException(feat_id=feat.id, ability_score_increase_id=ability_score_increase_id)


async def check_feat_prerequisite(character: Character, feat: Feat, stats_service: CharacterStatsService) -> None:
    """
    Raise ``FeatPrerequisiteNotMetException`` if the feat has an
    ability-score prerequisite the character's current *effective* score
    doesn't meet.

    Effective scores are computed fresh here (not read from the cache
    table, and not persisted) so this check is always based on the
    character's current race/feats, even if the cache happens to be
    stale. See ``CharacterStatsService.compute``.
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
