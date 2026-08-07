"""Unit tests for character progression schemas (race/class change, ASI/feat choices)."""

from pydantic import ValidationError
import pytest

from app.features.characters.progression.schemas import (
    ASIChoice,
    ASIIncreaseItem,
    CharacterASIChoiceResponse,
    ClassChange,
    FeatChoice,
    LevelUpRequest,
    RaceChange,
)


@pytest.mark.unit
class TestRaceChange:
    def test_defaults_to_no_race(self):
        assert RaceChange().race_id is None

    def test_accepts_race_id(self):
        assert RaceChange(race_id=7).race_id == 7

    def test_accepts_null_race_id(self):
        assert RaceChange(race_id=None).race_id is None


@pytest.mark.unit
class TestClassChange:
    def test_accepts_class_id(self):
        assert ClassChange(class_id=3).class_id == 3

    def test_missing_class_id_is_rejected(self):
        with pytest.raises(ValidationError):
            ClassChange()


@pytest.mark.unit
class TestASIIncreaseItem:
    def test_amount_defaults_to_one(self):
        assert ASIIncreaseItem(ability="STR").amount == 1

    def test_amount_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            ASIIncreaseItem(ability="STR", amount=0)

    def test_amount_above_two_is_rejected(self):
        with pytest.raises(ValidationError):
            ASIIncreaseItem(ability="STR", amount=3)


@pytest.mark.unit
class TestASIChoice:
    def test_accepts_single_two_point_increase(self):
        choice = ASIChoice(increases=[ASIIncreaseItem(ability="STR", amount=2)])

        assert choice.type == "ASI"
        assert choice.increases[0].amount == 2

    def test_accepts_split_increases(self):
        choice = ASIChoice(increases=[{"ability": "STR", "amount": 1}, {"ability": "CON", "amount": 1}])

        assert len(choice.increases) == 2

    def test_duplicate_ability_is_rejected(self):
        with pytest.raises(ValidationError):
            ASIChoice(increases=[{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 1}])

    def test_total_over_budget_is_rejected(self):
        with pytest.raises(ValidationError):
            ASIChoice(increases=[{"ability": "STR", "amount": 2}, {"ability": "CON", "amount": 1}])

    def test_empty_increases_are_rejected(self):
        with pytest.raises(ValidationError):
            ASIChoice(increases=[])


@pytest.mark.unit
class TestFeatChoice:
    def test_accepts_feat_id(self):
        choice = FeatChoice(feat_id=9)

        assert choice.type == "FEAT"
        assert choice.feat_id == 9

    def test_asi_increase_id_is_optional(self):
        assert FeatChoice(feat_id=9).ability_score_increase_id is None

    def test_missing_feat_id_is_rejected(self):
        with pytest.raises(ValidationError):
            FeatChoice()


@pytest.mark.unit
class TestLevelUpRequest:
    def test_defaults_are_empty(self):
        request = LevelUpRequest()

        assert request.hit_points_gained is None
        assert request.choice is None

    def test_accepts_asi_choice(self):
        request = LevelUpRequest(choice={"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]})

        assert request.choice.type == "ASI"

    def test_accepts_feat_choice(self):
        request = LevelUpRequest(choice={"type": "FEAT", "feat_id": 9})

        assert request.choice.type == "FEAT"

    def test_unknown_choice_type_is_rejected(self):
        with pytest.raises(ValidationError):
            LevelUpRequest(choice={"type": "OTHER", "feat_id": 9})

    def test_invalid_asi_increases_inside_request_are_rejected(self):
        with pytest.raises(ValidationError):
            LevelUpRequest(choice={"type": "ASI", "increases": [{"ability": "STR", "amount": 3}]})

    def test_zero_hp_gain_is_rejected(self):
        with pytest.raises(ValidationError):
            LevelUpRequest(hit_points_gained=0)


@pytest.mark.unit
class TestCharacterASIChoiceResponse:
    def test_asi_response_round_trips(self):
        choice = CharacterASIChoiceResponse(
            id=1,
            character_id=5,
            class_level=4,
            choice_type="ASI",
            increases=[{"ability": "STR", "amount": 2}],
        )

        assert choice.choice_type.value == "ASI"
        assert choice.increases[0].ability.value == "STR"

    def test_feat_response_defaults_increases_to_empty(self):
        choice = CharacterASIChoiceResponse(
            id=2,
            character_id=5,
            class_level=4,
            choice_type="FEAT",
            feat_id=9,
        )

        assert choice.increases == []
        assert choice.feat_id == 9
