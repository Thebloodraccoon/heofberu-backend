"""Shared validation helpers for GM feat-grant operations on a character."""

from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.gm_panel.exceptions import (
    FeatAsiChoiceRequiredException,
    FeatPrerequisiteNotMetException,
    InvalidAbilityScoreIncreaseException,
)
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException
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


def validate_asi_choice_required(feat: Feat, ability_score_increase_id: int | None) -> None:
    """
    A feat offering ability-score increase options MUST be taken with an
    explicit choice: raise ``FeatAsiChoiceRequiredException`` when such a
    feat is granted/taken with no ``ability_score_increase_id``, so its
    points can never be silently lost.
    """

    if ability_score_increase_id is None and feat.ability_score_increases:
        raise FeatAsiChoiceRequiredException(feat_id=feat.id, choices=len(feat.ability_score_increases))


async def validate_ability_score_increase_cap(
    feat: Feat, ability_score_increase_id: int, character: Character, stats_service: CharacterStatsService
) -> None:
    """
    Raise ``AbilityScoreCapExceededException`` if applying the selected
    ``FeatAbilityScoreIncrease`` would push the character's effective
    score above the ability's cap.

    Mirrors the level-up ASI check (``CharacterProgressionService._apply_asi``)
    and the GM panel's ±adjustment check (``GmPanelAsiService``): every
    structured source of points validates against *effective* totals
    (base + race/subrace + feat increases + counted ASI log + feature
    effects) and the per-ability cap (20 by default, raised by feature
    ``new_cap`` effects such as Primal Champion), computed fresh rather
    than read from the cache table.
    """

    increase = next((i for i in feat.ability_score_increases if i.id == ability_score_increase_id), None)
    if increase is None:
        return

    totals = await stats_service.compute(character)
    caps = await stats_service.resolve_ability_caps(character)
    total_field = TOTAL_FIELD_BY_ABILITY[increase.ability]
    current_total = totals[total_field]
    requested = current_total + increase.amount

    if requested > caps[increase.ability]:
        raise AbilityScoreCapExceededException(
            ability=increase.ability.value,
            current_total=current_total,
            requested=requested,
        )


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
