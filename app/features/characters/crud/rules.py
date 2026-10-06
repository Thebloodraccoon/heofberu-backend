"""Pure character rules (no DB): creation-time validation, starting HP and HP updates."""

from collections.abc import Iterable
from typing import Any

from app.constants import BackgroundSuggestionType, DiceType
from app.features.characters.crud.exceptions import (
    BackgroundSuggestionIdsRequiredException,
    InvalidBackgroundSuggestionException,
    InvalidHpUpdateException,
    ItemChoiceNotAvailableException,
    SkillNotAvailableForClassException,
    TooFewItemChoicesException,
    TooManySkillChoicesException,
)
from app.features.characters.crud.schemas import HpUpdate


def validate_chosen_skills(skill_ids: list[int], character_class: Any) -> list[int]:
    """
    Validate the player's class skill choices: every id must be one of the
    class's ``available_skills`` and there may be at most ``skill_choice_count``.
    """

    if not skill_ids:
        return []

    allowed = character_class.skill_choice_count
    if len(skill_ids) > allowed:
        raise TooManySkillChoicesException(class_id=character_class.id, allowed=allowed, requested=len(skill_ids))

    available_ids = {skill.id for skill in character_class.available_skills}
    for skill_id in skill_ids:
        if skill_id not in available_ids:
            raise SkillNotAvailableForClassException(class_id=character_class.id, skill_id=skill_id)

    return skill_ids


def resolve_background_suggestions(background: Any, suggestion_ids: list[int]) -> dict[str, str]:
    """
    Resolve the picked suggestion ids into the personality-card payload:
    exactly one id per :class:`BackgroundSuggestionType` (PERSONALITY_TRAIT,
    IDEAL, BOND, FLAW), each belonging to this background.
    """

    if len(suggestion_ids) != len(BackgroundSuggestionType):
        raise BackgroundSuggestionIdsRequiredException(background_id=background.id, requested=len(suggestion_ids))

    suggestions_by_id = {suggestion.id: suggestion for suggestion in background.suggestions}
    chosen_by_type: dict[BackgroundSuggestionType, str] = {}
    for suggestion_id in suggestion_ids:
        suggestion = suggestions_by_id.get(suggestion_id)
        if suggestion is None:
            raise InvalidBackgroundSuggestionException(background_id=background.id, suggestion_id=suggestion_id)

        suggestion_type = BackgroundSuggestionType(suggestion.suggestion_type)
        if suggestion_type in chosen_by_type:
            raise BackgroundSuggestionIdsRequiredException(background_id=background.id, requested=len(suggestion_ids))
        chosen_by_type[suggestion_type] = suggestion.text

    if set(chosen_by_type) != set(BackgroundSuggestionType):
        raise BackgroundSuggestionIdsRequiredException(background_id=background.id, requested=len(suggestion_ids))

    return {
        "personality_traits": chosen_by_type[BackgroundSuggestionType.PERSONALITY_TRAIT],
        "ideals": chosen_by_type[BackgroundSuggestionType.IDEAL],
        "bonds": chosen_by_type[BackgroundSuggestionType.BOND],
        "flaws": chosen_by_type[BackgroundSuggestionType.FLAW],
    }


def pick_item_options(groups: Iterable[Any], item_choice_ids: list[int]) -> list[Any]:
    """
    Resolve the starting-equipment "pick N of M" answers against the choice
    ``groups``: every id must be an option of some group and every group
    must be answered with exactly ``pick_count`` options.
    """

    groups = list(groups)
    option_by_id = {option.id: option for group in groups for option in group.options}

    chosen_options = []
    for option_id in item_choice_ids:
        option = option_by_id.get(option_id)
        if option is None:
            raise ItemChoiceNotAvailableException(option_id=option_id)
        chosen_options.append(option)

    chosen_per_group: dict[int, int] = {}
    for option in chosen_options:
        chosen_per_group[option.group_id] = chosen_per_group.get(option.group_id, 0) + 1

    for group in groups:
        chosen = chosen_per_group.get(group.id, 0)
        if chosen != group.pick_count:
            raise TooFewItemChoicesException(group_id=group.id, pick_count=group.pick_count, chosen=chosen)

    return chosen_options


def starting_max_hp(hit_dice: DiceType, constitution_total: int) -> int:
    """Level-1 max HP: the full hit die plus the effective CON modifier, at least 1."""

    die_faces = int(hit_dice.value[1:])
    return max(die_faces + (constitution_total - 10) // 2, 1)


def apply_hp_delta(current_hp: int, temp_hp: int, delta: int) -> tuple[int, int]:
    """
    Resolve a healing/damage delta per 5e rules: healing adds to ``current_hp``
    only; damage drains ``temp_hp`` first with the overflow hitting
    ``current_hp``. Returns unclamped values.
    """

    if delta >= 0:
        return current_hp + delta, temp_hp

    damage = -delta
    absorbed = min(temp_hp, damage)
    return current_hp - (damage - absorbed), temp_hp - absorbed


def validate_hp_update(data: HpUpdate) -> None:
    """Raise ``InvalidHpUpdateException`` unless exactly one of a delta or absolute values is given."""

    has_delta = data.delta is not None
    has_absolute = data.current_hp is not None or data.temp_hp is not None
    if has_delta and has_absolute:
        raise InvalidHpUpdateException()
    if not has_delta and not has_absolute:
        raise InvalidHpUpdateException("Provide either 'delta' or an absolute HP value.")


def resolve_hp_update(current_hp: int, temp_hp: int, max_hp: int, data: HpUpdate) -> tuple[int, int]:
    """
    Compute the new ``(current_hp, temp_hp)`` for a validated HP update.

    An absolute ``temp_hp`` is a gain that applies only when higher than the
    current pool (temp HP never stacks). ``current_hp`` is clamped to
    ``[0, max_hp]``; ``temp_hp`` to ``>= 0``.
    """

    if data.delta is not None:
        new_current, new_temp = apply_hp_delta(current_hp, temp_hp, data.delta)
    else:
        new_current = data.current_hp if data.current_hp is not None else current_hp
        new_temp = max(temp_hp, data.temp_hp) if data.temp_hp is not None else temp_hp

    return max(0, min(new_current, max_hp)), max(0, new_temp)
