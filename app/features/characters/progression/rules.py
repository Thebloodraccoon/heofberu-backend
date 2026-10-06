"""Pure progression rules: hit-point math, ASI levels and ASI cap checks (no DB access)."""

from collections.abc import Iterable

from app.constants import ASI_LEVELS, CHARACTER_MAX_LEVEL
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.feats.validation import ensure_within_cap
from app.features.characters.progression.exceptions import (
    InvalidHitPointGainException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
    RebuildAsiChoicesMismatchException,
)
from app.features.characters.progression.schemas import ASIIncreaseItem, RebuildASIChoice


def hit_die_sides(hit_dice) -> int:
    """Sides of a class hit die (``HitDice.D8`` / ``"D8"`` -> 8)."""

    return int(getattr(hit_dice, "value", hit_dice)[1:])


def constitution_modifier(totals: dict[str, int]) -> int:
    """CON modifier from the *effective* CON total."""

    return (totals["constitution_total"] - 10) // 2


def resolve_hp_gain(requested: int | None, die_sides: int, con_mod: int) -> int:
    """
    Default HP gain is half hit die + 1 + CON modifier (never less than 1 —
    the 5e minimum of one HP per level); a provided value must fit
    ``[1, die + CON]``, whose upper bound is also clamped to at least 1.
    """

    if requested is None:
        return max(1, die_sides // 2 + 1 + con_mod)

    max_gain = max(1, die_sides + con_mod)
    if not 1 <= requested <= max_gain:
        raise InvalidHitPointGainException(minimum=1, maximum=max_gain)

    return requested


def max_hp_bounds(die_sides: int, con_mod: int, level: int) -> tuple[int, int]:
    """
    The valid ``max_hp`` range for a rebuild: level 1 always grants the full
    hit die + CON modifier (floored at 1, never a range, per 5e); each level
    above it contributes between 1 and hit die + CON modifier (floored at 1)
    — the same bounds ``level_up`` enforces per level, applied across every
    level at once since a rebuild has no per-level roll history.
    """

    level_1_hp = max(die_sides + con_mod, 1)
    if level <= 1:
        return level_1_hp, level_1_hp

    levels_above_one = level - 1
    return level_1_hp + levels_above_one, level_1_hp + levels_above_one * level_1_hp


def required_asi_levels(character_level: int) -> set[int]:
    """The ASI levels (see ``ASI_LEVELS``) at or below ``character_level``."""

    return {level for level in ASI_LEVELS if level <= character_level}


def check_level_up_choice(new_level: int, has_choice: bool) -> None:
    """An ASI level requires a ``choice``; any other level rejects one."""

    is_asi_level = new_level in ASI_LEVELS
    if is_asi_level and not has_choice:
        raise LevelUpChoiceRequiredException(class_level=new_level)
    if not is_asi_level and has_choice:
        raise LevelUpChoiceNotAllowedException(class_level=new_level)


def check_rebuild_asi_levels(character_level: int, asi_choices: Iterable[RebuildASIChoice]) -> None:
    """Require exactly one entry per reached ASI level — no fewer (unresolved), no more (not reached)."""

    required = required_asi_levels(character_level)
    provided = {item.class_level for item in asi_choices}
    if provided != required:
        raise RebuildAsiChoicesMismatchException(required_levels=sorted(required), provided_levels=sorted(provided))


def default_max_level(character_level: int) -> int:
    """Max level assumed for a character without a ``character_max_levels`` row: its current level."""

    return min(character_level, CHARACTER_MAX_LEVEL)


def apply_asi_to_totals(totals: dict[str, int], increases: list[ASIIncreaseItem]) -> None:
    """
    Check an Ability Score Improvement against the standard cap of 20 and add
    it to ``totals`` in place (so a following choice sees its predecessors).
    Player choices are always capped at 20 regardless of any feature
    ``new_cap`` that lets a score reach 30 via GM intervention. Nothing is
    changed when any ability exceeds the cap.
    """

    for item in increases:
        ensure_within_cap(totals, item.ability, item.amount)

    for item in increases:
        totals[TOTAL_FIELD_BY_ABILITY[item.ability]] += item.amount
