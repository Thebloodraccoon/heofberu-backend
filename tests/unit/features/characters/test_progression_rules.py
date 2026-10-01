"""Unit tests for the pure progression rules (hit points, ASI levels, ASI cap)."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.feats.exceptions import AbilityScoreCapExceededException
from app.features.characters.progression.exceptions import (
    InvalidHitPointGainException,
    LevelUpChoiceNotAllowedException,
    LevelUpChoiceRequiredException,
    RebuildAsiChoicesMismatchException,
)
from app.features.characters.progression.rules import (
    apply_asi_to_totals,
    check_level_up_choice,
    check_rebuild_asi_levels,
    constitution_modifier,
    default_max_level,
    hit_die_sides,
    max_hp_bounds,
    required_asi_levels,
    resolve_hp_gain,
)
from app.features.characters.progression.schemas import ASIIncreaseItem

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


def totals(**overrides):
    base = {f"{name}_total": 10 for name in ABILITIES}
    base.update(overrides)
    return base


@pytest.mark.unit
class TestHitDie:
    def test_reads_enum_like_and_plain_values(self):
        assert hit_die_sides(SimpleNamespace(value="D10")) == 10
        assert hit_die_sides("D6") == 6

    @pytest.mark.parametrize(("score", "modifier"), [(1, -5), (8, -1), (10, 0), (15, 2), (20, 5)])
    def test_constitution_modifier(self, score, modifier):
        assert constitution_modifier(totals(constitution_total=score)) == modifier


@pytest.mark.unit
class TestResolveHpGain:
    def test_default_is_half_die_plus_one_plus_con(self):
        assert resolve_hp_gain(None, 10, 2) == 8

    def test_default_never_below_one(self):
        assert resolve_hp_gain(None, 6, -5) == 1

    def test_explicit_value_within_bounds(self):
        assert resolve_hp_gain(3, 10, 2) == 3

    @pytest.mark.parametrize("requested", [0, 13])
    def test_explicit_value_outside_bounds_raises(self, requested):
        with pytest.raises(InvalidHitPointGainException):
            resolve_hp_gain(requested, 10, 2)

    def test_upper_bound_is_clamped_to_one(self):
        assert resolve_hp_gain(1, 4, -5) == 1
        with pytest.raises(InvalidHitPointGainException):
            resolve_hp_gain(2, 4, -5)


@pytest.mark.unit
class TestMaxHpBounds:
    def test_level_one_is_a_single_value(self):
        assert max_hp_bounds(6, 2, 1) == (8, 8)

    def test_each_further_level_adds_one_to_die_plus_con(self):
        assert max_hp_bounds(8, 1, 3) == (9 + 2, 9 + 2 * 9)

    def test_negative_con_is_floored_at_one_per_level(self):
        assert max_hp_bounds(4, -5, 2) == (2, 2)


@pytest.mark.unit
class TestAsiLevels:
    def test_required_levels_up_to_character_level(self):
        assert required_asi_levels(3) == set()
        assert required_asi_levels(12) == {4, 8, 12}
        assert required_asi_levels(20) == {4, 8, 12, 16, 19}

    def test_level_up_choice_is_required_on_asi_levels_only(self):
        check_level_up_choice(4, True)
        check_level_up_choice(5, False)
        with pytest.raises(LevelUpChoiceRequiredException):
            check_level_up_choice(4, False)
        with pytest.raises(LevelUpChoiceNotAllowedException):
            check_level_up_choice(5, True)

    def test_rebuild_choices_must_cover_exactly_the_reached_levels(self):
        check_rebuild_asi_levels(8, [SimpleNamespace(class_level=4), SimpleNamespace(class_level=8)])
        with pytest.raises(RebuildAsiChoicesMismatchException):
            check_rebuild_asi_levels(8, [SimpleNamespace(class_level=4)])
        with pytest.raises(RebuildAsiChoicesMismatchException):
            check_rebuild_asi_levels(5, [SimpleNamespace(class_level=4), SimpleNamespace(class_level=8)])

    def test_default_max_level_is_the_current_level_capped_at_the_system_max(self):
        assert default_max_level(7) == 7
        assert default_max_level(99) == 20


@pytest.mark.unit
class TestApplyAsiToTotals:
    def test_adds_increases_in_place(self):
        current = totals(strength_total=14)

        apply_asi_to_totals(
            current, [ASIIncreaseItem(ability=AbilityScore.STR, amount=1), ASIIncreaseItem(ability=AbilityScore.DEX)]
        )

        assert (current["strength_total"], current["dexterity_total"]) == (15, 11)

    def test_exactly_twenty_is_allowed(self):
        current = totals(strength_total=18)

        apply_asi_to_totals(current, [ASIIncreaseItem(ability=AbilityScore.STR, amount=2)])

        assert current["strength_total"] == 20

    def test_over_cap_raises_and_changes_nothing(self):
        current = totals(strength_total=19, dexterity_total=10)

        with pytest.raises(AbilityScoreCapExceededException):
            apply_asi_to_totals(
                current,
                [ASIIncreaseItem(ability=AbilityScore.DEX), ASIIncreaseItem(ability=AbilityScore.STR, amount=2)],
            )

        assert (current["strength_total"], current["dexterity_total"]) == (19, 10)
