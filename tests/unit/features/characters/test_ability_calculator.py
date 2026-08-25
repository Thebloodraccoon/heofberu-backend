"""Unit tests for the pure CharacterAbilityScoreCalculator."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import (
    CharacterAbilityScoreCalculator,
    resolve_ability_caps,
)
from app.models.character_model import Character
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus
from app.models.subrace_association_models import SubraceAbilityBonus


def make_character(**overrides) -> Character:
    base = {
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


def make_race_bonus(ability: AbilityScore, bonus: int, race_id: int = 5) -> RaceAbilityBonus:
    return RaceAbilityBonus(race_id=race_id, ability=ability, bonus=bonus)


def make_subrace_bonus(ability: AbilityScore, bonus: int, subrace_id: int = 7) -> SubraceAbilityBonus:
    return SubraceAbilityBonus(subrace_id=subrace_id, ability=ability, bonus=bonus)


def make_feat_increase(ability: AbilityScore, amount: int = 1) -> FeatAbilityScoreIncrease:
    return FeatAbilityScoreIncrease(feat_id=1, ability=ability, amount=amount)


@pytest.mark.unit
class TestCharacterAbilityScoreCalculator:
    def test_no_bonuses_returns_base_scores(self):
        character = make_character()

        totals = CharacterAbilityScoreCalculator().compute(character, [], [], [])

        assert totals == {
            "strength_total": 14,
            "dexterity_total": 10,
            "constitution_total": 12,
            "intelligence_total": 8,
            "wisdom_total": 9,
            "charisma_total": 11,
        }

    def test_result_has_only_the_six_total_keys(self):
        totals = CharacterAbilityScoreCalculator().compute(make_character(), [], [], [])

        assert set(totals) == {
            "strength_total",
            "dexterity_total",
            "constitution_total",
            "intelligence_total",
            "wisdom_total",
            "charisma_total",
        }

    def test_race_bonus_applied_to_its_ability_only(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, [], [])

        assert totals["dexterity_total"] == 12
        assert totals["strength_total"] == 14

    def test_multiple_race_bonuses_applied(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2), make_race_bonus(AbilityScore.CON, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, [], [])

        assert totals["dexterity_total"] == 12
        assert totals["constitution_total"] == 13

    def test_subrace_bonus_applied_to_its_ability_only(self):
        character = make_character()
        subrace_bonuses = [make_subrace_bonus(AbilityScore.INT, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, [], subrace_bonuses, [])

        assert totals["intelligence_total"] == 9
        assert totals["strength_total"] == 14

    def test_race_and_subrace_bonuses_stack(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2)]
        subrace_bonuses = [make_subrace_bonus(AbilityScore.DEX, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, subrace_bonuses, [])

        assert totals["dexterity_total"] == 13

    def test_race_and_subrace_on_same_ability_sum_not_override(self):
        """Race +2 DEX and subrace +1 DEX must produce +3 total, not +1 (override)."""
        character = make_character(dexterity=10)
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2)]
        subrace_bonuses = [make_subrace_bonus(AbilityScore.DEX, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, subrace_bonuses, [])

        assert totals["dexterity_total"] == 13  # 10 + 2 + 1, NOT 10 + 1

    def test_race_and_subrace_on_different_abilities_both_apply(self):
        """Race bonus to STR and subrace bonus to DEX must both apply."""
        character = make_character(strength=10, dexterity=10)
        race_bonuses = [make_race_bonus(AbilityScore.STR, 2)]
        subrace_bonuses = [make_subrace_bonus(AbilityScore.DEX, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, subrace_bonuses, [])

        assert totals["strength_total"] == 12
        assert totals["dexterity_total"] == 11

    def test_feat_increase_applied(self):
        character = make_character()
        feat_increases = [make_feat_increase(AbilityScore.STR)]

        totals = CharacterAbilityScoreCalculator().compute(character, [], [], feat_increases)

        assert totals["strength_total"] == 15

    def test_race_subrace_and_feat_bonuses_stack(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2)]
        subrace_bonuses = [make_subrace_bonus(AbilityScore.CON, 1)]
        feat_increases = [make_feat_increase(AbilityScore.STR), make_feat_increase(AbilityScore.CON)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, subrace_bonuses, feat_increases)

        assert totals["strength_total"] == 15
        assert totals["dexterity_total"] == 12
        assert totals["constitution_total"] == 14

    def test_multiple_increases_on_same_ability_stack(self):
        character = make_character(strength=10)
        feat_increases = [make_feat_increase(AbilityScore.STR), make_feat_increase(AbilityScore.STR)]

        totals = CharacterAbilityScoreCalculator().compute(character, [], [], feat_increases)

        assert totals["strength_total"] == 12


def make_feature_increase(ability: AbilityScore, amount: int, new_cap: int | None = None):
    return SimpleNamespace(ability=ability, amount=amount, new_cap=new_cap)


def make_asi_log_increase(ability: AbilityScore, amount: int):
    return SimpleNamespace(ability=ability, amount=amount)


@pytest.mark.unit
class TestFeatureEffectAndAsiLogCounting:
    def test_all_five_sources_stack_into_one_total(self):
        """Race + subrace + feat ASI + counted log + feature effect all apply to one total."""
        character = make_character(strength=10)
        race_bonuses = [make_race_bonus(AbilityScore.STR, 1)]
        subrace_bonuses = [make_subrace_bonus(AbilityScore.STR, 1)]
        feat_increases = [make_feat_increase(AbilityScore.STR, amount=1)]
        asi_log = [make_asi_log_increase(AbilityScore.STR, 2)]
        feature_effects = [make_feature_increase(AbilityScore.STR, amount=4)]

        totals = CharacterAbilityScoreCalculator().compute(
            character, race_bonuses, subrace_bonuses, feat_increases, asi_log, feature_effects
        )

        assert totals["strength_total"] == 19

    def test_negative_feature_effect_lowers_total_but_floors_at_one(self):
        character = make_character(charisma=3)
        feature_effects = [
            make_feature_increase(AbilityScore.CHA, amount=-2),
            make_feature_increase(AbilityScore.INT, amount=-20),
        ]

        totals = CharacterAbilityScoreCalculator().compute(character, [], [], [], [], feature_effects)

        assert totals["charisma_total"] == 1
        assert totals["intelligence_total"] == 1

    def test_normal_totals_are_not_affected_by_the_floor(self):
        totals = CharacterAbilityScoreCalculator().compute(make_character(), [], [], [])

        assert totals == {
            "strength_total": 14,
            "dexterity_total": 10,
            "constitution_total": 12,
            "intelligence_total": 8,
            "wisdom_total": 9,
            "charisma_total": 11,
        }


@pytest.mark.unit
class TestResolveAbilityCaps:
    def test_without_effects_every_cap_is_twenty(self):
        caps = resolve_ability_caps([])

        assert caps == dict.fromkeys(AbilityScore, 20)

    def test_new_cap_raises_the_standard_cap(self):
        effects = [
            make_feature_increase(AbilityScore.STR, amount=4, new_cap=24),
            make_feature_increase(AbilityScore.CON, amount=4, new_cap=24),
        ]

        caps = resolve_ability_caps(effects)

        assert caps[AbilityScore.STR] == 24
        assert caps[AbilityScore.CON] == 24
        assert caps[AbilityScore.DEX] == 20

    def test_lower_new_cap_is_ignored(self):
        caps = resolve_ability_caps([make_feature_increase(AbilityScore.WIS, amount=1, new_cap=18)])

        assert caps[AbilityScore.WIS] == 20

    def test_multiple_caps_take_the_maximum(self):
        effects = [
            make_feature_increase(AbilityScore.STR, amount=2, new_cap=22),
            make_feature_increase(AbilityScore.STR, amount=2, new_cap=24),
        ]

        assert resolve_ability_caps(effects)[AbilityScore.STR] == 24

    def test_effect_without_new_cap_keeps_default(self):
        caps = resolve_ability_caps([make_feature_increase(AbilityScore.CHA, amount=2, new_cap=None)])

        assert caps[AbilityScore.CHA] == 20
