"""
Pure calculation of a character's computed armor class and speeds (no DB access).

Everything is decided by what the caller passes in: the character's level and
ability totals, its race's walking speed, its EQUIPPED items, and the speed /
AC effect rows that currently reach it — from its feature grants and from its
active items (equipped, and attuned when the item requires attunement), each
paired with the label shown in the breakdown (the feature's / item's name).

Armor class: the best base among "no armor" (10 + DEX, only when no body armor
is worn), the worn armor (light: + DEX, medium: + DEX up to its cap, heavy: no
DEX; + its ``magic_bonus``) and every applicable ``FORMULA`` effect; then a
worn shield (when the chosen base allows one) and every applicable ``BONUS``.

Speeds: walking starts at the race's speed, raised by ``SET`` effects, then
lowered by 10 ft for heavy armor worn below its Strength requirement (unless
an ``IGNORE_ARMOR_PENALTY`` effect applies), then ``BONUS`` effects. Every
other speed exists only through ``SET`` / ``EQUAL_TO_WALK`` effects, then
gets its ``BONUS`` effects. No speed goes below 0.

Whatever reaches the character but doesn't count right now — an effect whose
condition or level isn't met, a base AC that lost to a better one, a shield
the chosen base excludes, a bonus to a speed the character doesn't have, a set
speed below the current one — is listed in ``inactive`` with its ``reason``.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.constants import (
    AbilityScore,
    ArmorClassEffectMode,
    ArmorProficiency,
    EffectCondition,
    SpeedEffectMode,
    SpeedType,
)

UNARMORED_BASE = 10
DEFAULT_MEDIUM_ARMOR_DEX_CAP = 2
HEAVY_ARMOR_SPEED_PENALTY = 10
_LOST_BASE_REASON = "основа КД ниже"
BASE_SPEED_LABEL = "Базовая скорость"  # the walking-speed base line without a (still existing) race
_BODY_ARMOR = (ArmorProficiency.LIGHT, ArmorProficiency.MEDIUM, ArmorProficiency.HEAVY)

ABILITY_LABELS_RU = {
    AbilityScore.STR: "Сила",
    AbilityScore.DEX: "Ловкость",
    AbilityScore.CON: "Телосложение",
    AbilityScore.INT: "Интеллект",
    AbilityScore.WIS: "Мудрость",
    AbilityScore.CHA: "Харизма",
}

# Why a conditional effect doesn't apply right now.
_CONDITION_REASONS_RU = {
    EffectCondition.WEARING_ARMOR: "нужен надетый доспех",
    EffectCondition.NO_ARMOR: "только без доспеха",
    EffectCondition.NO_HEAVY_ARMOR: "только без тяжёлого доспеха",
    EffectCondition.NO_ARMOR_NO_SHIELD: "только без доспеха и щита",
}

# Genitive: "нет скорости полёта".
_SPEED_GENITIVE_RU = {
    SpeedType.WALK: "ходьбы",
    SpeedType.FLY: "полёта",
    SpeedType.SWIM: "плавания",
    SpeedType.CLIMB: "лазания",
    SpeedType.BURROW: "копания",
}


def ability_modifier(total: int) -> int:
    """The 5e modifier of an ability score."""

    return (total - 10) // 2


@dataclass(frozen=True)
class Contribution:
    """
    One line of a breakdown: where it comes from (``source``: kind, ``label``: name) and how much; ``reason`` is
    set on an ``inactive`` line only — why it doesn't count right now — with ``reason_code`` its machine-readable
    form: ``base_lower``, ``condition_unmet``, ``level_too_low``, ``not_stacking``, ``speed_higher``, ``no_speed``.
    """

    source: str
    label: str
    value: int
    speed_type: SpeedType | None = None
    reason: str | None = None
    reason_code: str | None = None


@dataclass
class ArmorClassResult:
    """The computed AC, the lines that sum to it and the ones that don't count right now."""

    total: int
    breakdown: list[Contribution] = field(default_factory=list)
    inactive: list[Contribution] = field(default_factory=list)


@dataclass
class SpeedResult:
    """Every computed speed (``None`` = the character doesn't have it), how each was reached, what doesn't count."""

    speeds: dict[SpeedType, int | None]
    breakdown: list[Contribution] = field(default_factory=list)
    inactive: list[Contribution] = field(default_factory=list)


@dataclass(frozen=True)
class Equipment:
    """What the character wears: the best body armor and the best shield among its equipped items."""

    armor: Any = None
    shield: Any = None

    @classmethod
    def from_items(cls, items: Iterable[Any]) -> "Equipment":
        """Pick, among equipped items, the body armor with the highest base and the shield with the highest bonus."""

        items = list(items)

        def best(category_ok) -> Any:
            candidates = [item for item in items if category_ok(item.armor_category)]
            return max(candidates, key=_armor_value, default=None)

        return cls(
            armor=best(lambda category: category in _BODY_ARMOR),
            shield=best(lambda category: category == ArmorProficiency.SHIELD),
        )

    def holds(self, condition: EffectCondition) -> bool:
        """Whether an effect's ``condition`` holds for this equipment."""

        if condition == EffectCondition.WEARING_ARMOR:
            return self.armor is not None
        if condition == EffectCondition.NO_ARMOR:
            return self.armor is None
        if condition == EffectCondition.NO_HEAVY_ARMOR:
            return self.armor is None or self.armor.armor_category != ArmorProficiency.HEAVY
        if condition == EffectCondition.NO_ARMOR_NO_SHIELD:
            return self.armor is None and self.shield is None
        return True


def _armor_value(item: Any) -> int:
    """An armor's or shield's own AC number: its base plus its magic bonus."""

    return (item.armor_class_base or 0) + (item.magic_bonus or 0)


def _refusal(effect: Any, equipment: Equipment, level: int) -> tuple[str, str] | None:
    """``(reason, reason_code)`` why ``effect`` doesn't apply right now (condition or level), ``None`` when it does."""

    if not equipment.holds(effect.condition):
        return _CONDITION_REASONS_RU.get(effect.condition, "условие не выполнено"), "condition_unmet"
    if effect.min_level is not None and level < effect.min_level:
        return f"с {effect.min_level}-го уровня", "level_too_low"
    return None


def _split(
    effects: Iterable[tuple[str, Any]], equipment: Equipment, level: int
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any, str, str]]]:
    """The ``(label, effect)`` pairs that apply, and ``(label, effect, reason, reason_code)`` for those that don't."""

    applicable, refused = [], []
    for label, effect in effects:
        refusal = _refusal(effect, equipment, level)
        if refusal is None:
            applicable.append((label, effect))
        else:
            refused.append((label, effect, *refusal))
    return applicable, refused


def collect_effects(
    grants: Iterable[tuple[Any, Any]], stacks: Iterable[Any]
) -> tuple[list[Any], list[tuple[str, Any]], list[tuple[str, Any]]]:
    """
    ``(equipped_items, speed_effects, ac_effects)`` from the character's grant effects (``(feature, effects)``
    pairs with ``speeds`` / ``armor_class``) and its equipped stacks. An item that requires attunement gives
    its effects only while attuned (its armor numbers count anyway); each effect is labelled with its
    feature's / item's name. Pure.
    """

    stacks = list(stacks)
    equipped = [stack.item for stack in stacks]
    active = [stack.item for stack in stacks if stack.is_attuned or not stack.item.requires_attunement]

    speed_effects: list[tuple[str, Any]] = []
    ac_effects: list[tuple[str, Any]] = []
    for feature, effects in grants:
        speed_effects += [(feature.name, row) for row in effects.speeds]
        ac_effects += [(feature.name, row) for row in effects.armor_class]
    for item in active:
        speed_effects += [(item.name, row) for row in item.speed_effects]
        ac_effects += [(item.name, row) for row in item.armor_class_effects]
    return equipped, speed_effects, ac_effects


def compute_armor_class(
    totals: dict[AbilityScore, int],
    level: int,
    equipped: Iterable[Any],
    effects: Iterable[tuple[str, Any]],
) -> ArmorClassResult:
    """The character's computed AC (see the module docstring)."""

    equipment = Equipment.from_items(equipped)
    applicable, refused = _split(effects, equipment, level)
    dex = ability_modifier(totals[AbilityScore.DEX])

    # (lines making up the base, whether a shield may still add)
    candidates: list[tuple[list[Contribution], bool]] = []
    armor = equipment.armor
    if armor is None:
        candidates.append(
            (
                [
                    Contribution("unarmored", "Без доспеха", UNARMORED_BASE),
                    Contribution("ability", ABILITY_LABELS_RU[AbilityScore.DEX], dex),
                ],
                True,
            )
        )
    else:
        lines = [Contribution("armor", armor.name, _armor_value(armor))]
        if armor.armor_category == ArmorProficiency.LIGHT:
            lines.append(Contribution("ability", ABILITY_LABELS_RU[AbilityScore.DEX], dex))
        elif armor.armor_category == ArmorProficiency.MEDIUM:
            cap = armor.armor_class_max_dex_bonus
            cap = DEFAULT_MEDIUM_ARMOR_DEX_CAP if cap is None else cap
            lines.append(Contribution("ability", ABILITY_LABELS_RU[AbilityScore.DEX], min(dex, cap)))
        candidates.append((lines, True))

    for label, effect in applicable:
        if effect.mode == ArmorClassEffectMode.FORMULA:
            lines = [Contribution("formula", label, effect.value)]
            lines += [
                Contribution("ability", ABILITY_LABELS_RU[ability], ability_modifier(totals[ability]))
                for ability in effect.abilities
            ]
            candidates.append((lines, effect.allows_shield))

    base_lines, allows_shield = max(candidates, key=lambda candidate: sum(line.value for line in candidate[0]))
    breakdown = list(base_lines)
    inactive = [
        Contribution(
            lines[0].source,
            lines[0].label,
            sum(line.value for line in lines),
            reason=_LOST_BASE_REASON,
            reason_code="base_lower",
        )
        for lines, _ in candidates
        if lines is not base_lines
    ]

    if equipment.shield is not None:
        shield = Contribution("shield", equipment.shield.name, _armor_value(equipment.shield))
        if allows_shield:
            breakdown.append(shield)
        else:
            reason = f"не складывается с «{base_lines[0].label}»"
            inactive.append(
                Contribution(shield.source, shield.label, shield.value, reason=reason, reason_code="not_stacking")
            )

    breakdown += [
        Contribution("bonus", label, effect.value)
        for label, effect in applicable
        if effect.mode == ArmorClassEffectMode.BONUS
    ]
    inactive += [
        Contribution(effect.mode.value.lower(), label, effect.value, reason=reason, reason_code=code)
        for label, effect, reason, code in refused
    ]

    return ArmorClassResult(total=sum(line.value for line in breakdown), breakdown=breakdown, inactive=inactive)


def compute_speeds(
    totals: dict[AbilityScore, int],
    level: int,
    base_walk: int,
    base_label: str,
    equipped: Iterable[Any],
    effects: Iterable[tuple[str, Any]],
) -> SpeedResult:
    """The character's computed speeds (see the module docstring)."""

    equipment = Equipment.from_items(equipped)
    applicable, refused = _split(effects, equipment, level)
    speeds: dict[SpeedType, int | None] = dict.fromkeys(SpeedType)
    breakdown: list[Contribution] = []
    inactive = [
        Contribution(effect.mode.value.lower(), label, effect.value, effect.speed_type, reason, code)
        for label, effect, reason, code in refused
    ]

    def by(speed_type: SpeedType, mode: SpeedEffectMode) -> list[tuple[str, Any]]:
        return [(label, e) for label, e in applicable if e.speed_type == speed_type and e.mode == mode]

    def raise_to(speed_type: SpeedType, value: int, source: str, label: str) -> None:
        current = speeds[speed_type]
        if current is None or value > current:
            speeds[speed_type] = value
            breakdown.append(Contribution(source, label, value, speed_type))
        else:
            inactive.append(Contribution(source, label, value, speed_type, "скорость уже выше", "speed_higher"))

    def add_bonuses(speed_type: SpeedType) -> None:
        for label, effect in by(speed_type, SpeedEffectMode.BONUS):
            if speeds[speed_type] is None:
                reason = f"нет скорости {_SPEED_GENITIVE_RU[speed_type]}"
                inactive.append(Contribution("bonus", label, effect.value, speed_type, reason, "no_speed"))
                continue
            speeds[speed_type] = max(0, speeds[speed_type] + effect.value)
            breakdown.append(Contribution("bonus", label, effect.value, speed_type))

    raise_to(SpeedType.WALK, base_walk, "base", base_label)
    for label, effect in by(SpeedType.WALK, SpeedEffectMode.SET):
        raise_to(SpeedType.WALK, effect.value, "set", label)

    armor = equipment.armor
    too_weak = (
        armor is not None
        and armor.armor_category == ArmorProficiency.HEAVY
        and armor.strength_requirement is not None
        and totals[AbilityScore.STR] < armor.strength_requirement
    )
    ignores_penalty = any(effect.mode == SpeedEffectMode.IGNORE_ARMOR_PENALTY for _, effect in applicable)
    if too_weak and not ignores_penalty:
        speeds[SpeedType.WALK] = max(0, (speeds[SpeedType.WALK] or 0) - HEAVY_ARMOR_SPEED_PENALTY)
        breakdown.append(Contribution("penalty", armor.name, -HEAVY_ARMOR_SPEED_PENALTY, SpeedType.WALK))
    add_bonuses(SpeedType.WALK)

    walk = speeds[SpeedType.WALK] or 0
    for speed_type in SpeedType:
        if speed_type == SpeedType.WALK:
            continue
        for label, effect in by(speed_type, SpeedEffectMode.SET):
            raise_to(speed_type, effect.value, "set", label)
        for label, _ in by(speed_type, SpeedEffectMode.EQUAL_TO_WALK):
            raise_to(speed_type, walk, "equal_to_walk", label)
        add_bonuses(speed_type)

    return SpeedResult(speeds=speeds, breakdown=breakdown, inactive=inactive)
