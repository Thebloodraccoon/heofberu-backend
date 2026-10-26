"""Unit tests for the pure AC / speed calculator (``characters.combat.calculator``)."""

from types import SimpleNamespace

import pytest

from app.constants import (
    AbilityScore,
    ArmorClassEffectMode,
    ArmorProficiency,
    EffectCondition,
    SpeedEffectMode,
    SpeedType,
)
from app.features.characters.combat.calculator import collect_effects, compute_armor_class, compute_speeds


def totals(**overrides) -> dict[AbilityScore, int]:
    scores = dict.fromkeys(AbilityScore, 10)
    scores.update({AbilityScore[name]: value for name, value in overrides.items()})
    return scores


def armor(name, category, base, *, max_dex=None, strength=None, magic=None):
    return SimpleNamespace(
        name=name,
        armor_category=category,
        armor_class_base=base,
        armor_class_max_dex_bonus=max_dex,
        strength_requirement=strength,
        magic_bonus=magic,
    )


def weapon(name="Длинный меч"):
    return SimpleNamespace(name=name, armor_category=None)


def ac_effect(
    mode=ArmorClassEffectMode.BONUS, value=0, abilities=(), *, allows_shield=True, condition=None, level=None
):
    return SimpleNamespace(
        mode=mode,
        value=value,
        abilities=list(abilities),
        allows_shield=allows_shield,
        condition=condition or EffectCondition.NONE,
        min_level=level,
    )


def speed_effect(speed_type=SpeedType.WALK, mode=SpeedEffectMode.BONUS, value=0, *, condition=None, level=None):
    return SimpleNamespace(
        speed_type=speed_type,
        mode=mode,
        value=value,
        condition=condition or EffectCondition.NONE,
        min_level=level,
    )


UNARMORED_DEFENSE = ac_effect(
    ArmorClassEffectMode.FORMULA, 10, [AbilityScore.DEX, AbilityScore.CON], condition=EffectCondition.NO_ARMOR
)
SHIELD = armor("Щит", ArmorProficiency.SHIELD, 2)


@pytest.mark.unit
class TestArmorClass:
    def test_unarmored_is_ten_plus_dex(self):
        result = compute_armor_class(totals(DEX=14), 1, [], [])

        assert result.total == 12

    def test_light_armor_adds_full_dex(self):
        assert compute_armor_class(totals(DEX=18), 1, [armor("Кожаный", ArmorProficiency.LIGHT, 11)], []).total == 15

    def test_medium_armor_caps_dex_at_two_by_default(self):
        worn = [armor("Кольчужная рубаха", ArmorProficiency.MEDIUM, 13)]

        assert compute_armor_class(totals(DEX=18), 1, worn, []).total == 15

    def test_medium_armor_uses_its_own_cap(self):
        worn = [armor("Полулаты", ArmorProficiency.MEDIUM, 15, max_dex=3)]

        assert compute_armor_class(totals(DEX=18), 1, worn, []).total == 18

    def test_heavy_armor_ignores_dex_and_adds_magic_bonus(self):
        worn = [armor("Латы +1", ArmorProficiency.HEAVY, 18, magic=1)]

        assert compute_armor_class(totals(DEX=8), 1, worn, []).total == 19

    def test_shield_adds_and_non_armor_items_are_ignored(self):
        result = compute_armor_class(totals(), 1, [SHIELD, weapon()], [])

        assert result.total == 12
        assert [line.source for line in result.breakdown] == ["unarmored", "ability", "shield"]

    def test_unarmored_defense_beats_plain_unarmored_and_keeps_the_shield(self):
        result = compute_armor_class(totals(DEX=14, CON=16), 1, [SHIELD], [("Защита без доспехов", UNARMORED_DEFENSE)])

        assert result.total == 10 + 2 + 3 + 2

    def test_formula_does_not_apply_in_armor(self):
        worn = [armor("Кожаный", ArmorProficiency.LIGHT, 11)]

        result = compute_armor_class(totals(DEX=14, CON=18), 1, worn, [("Защита без доспехов", UNARMORED_DEFENSE)])

        assert result.total == 13

    def test_monk_formula_drops_the_shield(self):
        monk = ac_effect(ArmorClassEffectMode.FORMULA, 10, [AbilityScore.DEX, AbilityScore.WIS], allows_shield=False)

        result = compute_armor_class(totals(DEX=16, WIS=16), 1, [SHIELD], [("Монах", monk)])

        # the formula (16) still beats unarmored + shield (13 + 2), but no shield on top of it
        assert result.total == 16

    def test_conditional_bonus_and_level_threshold(self):
        defense = ac_effect(value=1, condition=EffectCondition.WEARING_ARMOR)
        late = ac_effect(value=1, level=5)
        worn = [armor("Кольчуга", ArmorProficiency.HEAVY, 16)]

        assert compute_armor_class(totals(), 4, worn, [("Защита", defense), ("Поздно", late)]).total == 17
        assert compute_armor_class(totals(), 5, worn, [("Защита", defense), ("Поздно", late)]).total == 18
        assert compute_armor_class(totals(), 5, [], [("Защита", defense)]).total == 10


@pytest.mark.unit
class TestSpeeds:
    def test_race_speed_is_the_walking_base(self):
        result = compute_speeds(totals(), 1, 25, "Дварф", [], [])

        assert result.speeds[SpeedType.WALK] == 25
        assert result.speeds[SpeedType.FLY] is None

    def test_fast_movement_only_without_heavy_armor(self):
        fast = speed_effect(value=10, condition=EffectCondition.NO_HEAVY_ARMOR)
        heavy = [armor("Латы", ArmorProficiency.HEAVY, 18)]

        assert compute_speeds(totals(), 5, 30, "Человек", [], [("Быстрое", fast)]).speeds[SpeedType.WALK] == 40
        assert compute_speeds(totals(), 5, 30, "Человек", heavy, [("Быстрое", fast)]).speeds[SpeedType.WALK] == 30

    def test_heavy_armor_below_strength_slows_unless_ignored(self):
        heavy = [armor("Латы", ArmorProficiency.HEAVY, 18, strength=15)]
        dwarf = speed_effect(mode=SpeedEffectMode.IGNORE_ARMOR_PENALTY)

        assert compute_speeds(totals(STR=13), 1, 30, "Человек", heavy, []).speeds[SpeedType.WALK] == 20
        assert compute_speeds(totals(STR=15), 1, 30, "Человек", heavy, []).speeds[SpeedType.WALK] == 30
        assert compute_speeds(totals(STR=13), 1, 25, "Дварф", heavy, [("Дварф", dwarf)]).speeds[SpeedType.WALK] == 25

    def test_set_is_a_minimum(self):
        striding = speed_effect(mode=SpeedEffectMode.SET, value=30)

        assert compute_speeds(totals(), 1, 25, "Дварф", [], [("Сапоги", striding)]).speeds[SpeedType.WALK] == 30
        assert compute_speeds(totals(), 1, 35, "Эльф", [], [("Сапоги", striding)]).speeds[SpeedType.WALK] == 35

    def test_other_speeds_come_from_effects_only(self):
        effects = [
            ("Аарракокра", speed_effect(SpeedType.FLY, SpeedEffectMode.SET, 50)),
            ("Паук", speed_effect(SpeedType.CLIMB, SpeedEffectMode.EQUAL_TO_WALK)),
            ("Ласты", speed_effect(SpeedType.SWIM, SpeedEffectMode.BONUS, 10)),
            ("Быстрое", speed_effect(value=10)),
        ]

        result = compute_speeds(totals(), 1, 30, "Человек", [], effects)

        assert result.speeds[SpeedType.WALK] == 40
        assert result.speeds[SpeedType.FLY] == 50
        assert result.speeds[SpeedType.CLIMB] == 40
        assert result.speeds[SpeedType.SWIM] is None  # a bonus needs an existing speed

    def test_monk_movement_scales_by_level(self):
        rows = [
            ("Движение без доспехов", speed_effect(value=10, level=2, condition=EffectCondition.NO_ARMOR_NO_SHIELD)),
            ("Движение без доспехов", speed_effect(value=5, level=6, condition=EffectCondition.NO_ARMOR_NO_SHIELD)),
        ]

        assert compute_speeds(totals(), 1, 30, "Человек", [], rows).speeds[SpeedType.WALK] == 30
        assert compute_speeds(totals(), 6, 30, "Человек", [], rows).speeds[SpeedType.WALK] == 45
        assert compute_speeds(totals(), 6, 30, "Человек", [SHIELD], rows).speeds[SpeedType.WALK] == 30


@pytest.mark.unit
class TestInactive:
    def test_unmet_condition_and_level_are_listed_with_their_reason(self):
        in_armor = ac_effect(value=10, condition=EffectCondition.WEARING_ARMOR)
        late = ac_effect(value=8, level=3)

        result = compute_armor_class(totals(), 1, [], [("Камень", in_armor), ("Камень", late)])

        assert result.total == 10
        assert [(line.value, line.reason, line.reason_code) for line in result.inactive] == [
            (10, "нужен надетый доспех", "condition_unmet"),
            (8, "с 3-го уровня", "level_too_low"),
        ]

    def test_losing_base_and_excluded_shield_are_listed(self):
        monk = ac_effect(ArmorClassEffectMode.FORMULA, 10, [AbilityScore.DEX, AbilityScore.WIS], allows_shield=False)

        result = compute_armor_class(totals(DEX=16, WIS=16), 1, [SHIELD], [("Монах", monk)])

        assert [(line.source, line.value, line.reason, line.reason_code) for line in result.inactive] == [
            ("unarmored", 13, "основа КД ниже", "base_lower"),
            ("shield", 2, "не складывается с «Монах»", "not_stacking"),
        ]

    def test_bonus_to_a_missing_speed_and_a_lower_set_are_listed(self):
        effects = [
            ("Крылья", speed_effect(SpeedType.FLY, SpeedEffectMode.BONUS, 10)),
            ("Сапоги", speed_effect(mode=SpeedEffectMode.SET, value=30)),
        ]

        result = compute_speeds(totals(), 1, 40, "Волот", [], effects)

        assert result.speeds[SpeedType.FLY] is None
        assert [(line.speed_type, line.value, line.reason, line.reason_code) for line in result.inactive] == [
            (SpeedType.WALK, 30, "скорость уже выше", "speed_higher"),
            (SpeedType.FLY, 10, "нет скорости полёта", "no_speed"),
        ]

    def test_refused_speed_effect_carries_its_code(self):
        fast = speed_effect(value=10, condition=EffectCondition.NO_HEAVY_ARMOR)
        heavy = [armor("Латы", ArmorProficiency.HEAVY, 18)]

        result = compute_speeds(totals(), 1, 30, "Человек", heavy, [("Быстрое", fast)])

        assert [(line.reason, line.reason_code) for line in result.inactive] == [
            ("только без тяжёлого доспеха", "condition_unmet")
        ]

    def test_applied_lines_carry_no_reason(self):
        result = compute_speeds(totals(), 1, 30, "Человек", [], [("Быстрое", speed_effect(value=10))])

        assert result.inactive == []
        assert all(line.reason is None and line.reason_code is None for line in result.breakdown)


def stack(item, *, attuned=False):
    return SimpleNamespace(item=item, is_attuned=attuned)


def magic_item(name, *, requires_attunement, speeds=(), acs=()):
    return SimpleNamespace(
        name=name,
        armor_category=None,
        requires_attunement=requires_attunement,
        speed_effects=list(speeds),
        armor_class_effects=list(acs),
    )


@pytest.mark.unit
class TestCollectEffects:
    def test_grant_and_item_effects_are_labelled_with_their_source(self):
        fast, ring = speed_effect(value=10), ac_effect(value=1)
        grant = (SimpleNamespace(name="Быстрое передвижение"), SimpleNamespace(speeds=[fast], armor_class=[]))
        item = magic_item("Кольцо защиты", requires_attunement=False, acs=[ring])

        equipped, speeds, acs = collect_effects([grant], [stack(item)])

        assert equipped == [item]
        assert speeds == [("Быстрое передвижение", fast)]
        assert acs == [("Кольцо защиты", ring)]

    def test_an_unattuned_item_needing_attunement_still_counts_as_worn_but_gives_no_effects(self):
        ring = ac_effect(value=1)
        cloak = magic_item("Плащ защиты", requires_attunement=True, acs=[ring])

        unattuned = collect_effects([], [stack(cloak)])
        attuned = collect_effects([], [stack(cloak, attuned=True)])

        assert unattuned == ([cloak], [], [])
        assert attuned == ([cloak], [], [("Плащ защиты", ring)])
