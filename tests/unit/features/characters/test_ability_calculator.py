"""Unit tests for the pure CharacterAbilityScoreCalculator."""

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import CharacterAbilityScoreCalculator
from app.models.character_model import Character
from app.models.feat_model import FeatAbilityScoreIncrease
from app.models.race_association_models import RaceAbilityBonus


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


def make_feat_increase(ability: AbilityScore, amount: int = 1) -> FeatAbilityScoreIncrease:
    return FeatAbilityScoreIncrease(feat_id=1, ability=ability, amount=amount)


@pytest.mark.unit
class TestCharacterAbilityScoreCalculator:
    def test_no_bonuses_returns_base_scores(self):
        character = make_character()

        totals = CharacterAbilityScoreCalculator().compute(character, [], [])

        assert totals == {
            "strength_total": 14,
            "dexterity_total": 10,
            "constitution_total": 12,
            "intelligence_total": 8,
            "wisdom_total": 9,
            "charisma_total": 11,
        }

    def test_result_has_only_the_six_total_keys(self):
        totals = CharacterAbilityScoreCalculator().compute(make_character(), [], [])

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

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, [])

        assert totals["dexterity_total"] == 12
        assert totals["strength_total"] == 14

    def test_multiple_race_bonuses_applied(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2), make_race_bonus(AbilityScore.CON, 1)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, [])

        assert totals["dexterity_total"] == 12
        assert totals["constitution_total"] == 13

    def test_feat_increase_applied(self):
        character = make_character()
        feat_increases = [make_feat_increase(AbilityScore.STR)]

        totals = CharacterAbilityScoreCalculator().compute(character, [], feat_increases)

        assert totals["strength_total"] == 15

    def test_race_and_feat_bonuses_stack(self):
        character = make_character()
        race_bonuses = [make_race_bonus(AbilityScore.DEX, 2)]
        feat_increases = [make_feat_increase(AbilityScore.STR), make_feat_increase(AbilityScore.CON)]

        totals = CharacterAbilityScoreCalculator().compute(character, race_bonuses, feat_increases)

        assert totals["strength_total"] == 15
        assert totals["dexterity_total"] == 12
        assert totals["constitution_total"] == 13

    def test_multiple_increases_on_same_ability_stack(self):
        character = make_character(strength=10)
        feat_increases = [make_feat_increase(AbilityScore.STR), make_feat_increase(AbilityScore.STR)]

        totals = CharacterAbilityScoreCalculator().compute(character, [], feat_increases)

        assert totals["strength_total"] == 12
