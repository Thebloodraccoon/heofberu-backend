"""Unit tests for the derived combat stats calculator (AC computation)."""

import pytest

from app.features.characters.ability_score.calculator import (
    DEFAULT_SPEED,
    UNARMORED_AC_BASE,
    ArmorSpec,
    compute_armor_class,
)


@pytest.mark.unit
class TestComputeArmorClass:
    def test_unarmored_uses_ten_plus_dex_modifier(self):
        assert compute_armor_class(dex_total=10, armor=None) == UNARMORED_AC_BASE + 0

    def test_unarmored_high_dexterity(self):
        assert compute_armor_class(dex_total=14, armor=None) == UNARMORED_AC_BASE + 2

    def test_unarmored_low_dexterity_reduces_ac(self):
        assert compute_armor_class(dex_total=6, armor=None) == UNARMORED_AC_BASE - 2

    def test_light_armor_adds_full_dex_modifier(self):
        armor = ArmorSpec(base=11, dex_bonus=True, max_dex_bonus=None)

        assert compute_armor_class(dex_total=14, armor=armor) == 13

    def test_armor_with_dex_cap_uses_the_cap(self):
        armor = ArmorSpec(base=14, dex_bonus=True, max_dex_bonus=2)

        assert compute_armor_class(dex_total=18, armor=armor) == 16

    def test_armor_with_dex_cap_below_modifier(self):
        armor = ArmorSpec(base=14, dex_bonus=True, max_dex_bonus=2)

        assert compute_armor_class(dex_total=12, armor=armor) == 15

    def test_heavy_armor_ignores_dex_modifier(self):
        armor = ArmorSpec(base=18, dex_bonus=False, max_dex_bonus=None)

        assert compute_armor_class(dex_total=20, armor=armor) == 18


@pytest.mark.unit
class TestConstants:
    def test_default_speed_is_thirty(self):
        assert DEFAULT_SPEED == 30

    def test_unarmored_ac_base_is_ten(self):
        assert UNARMORED_AC_BASE == 10
