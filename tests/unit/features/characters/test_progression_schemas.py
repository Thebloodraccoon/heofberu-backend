"""Unit tests for character progression schemas (background setup, ASI/feat choices)."""

from pydantic import ValidationError
import pytest

from app.features.characters.progression.schemas import (
    MAX_FEATURE_CHOICES,
    MAX_HIT_POINTS_GAINED,
    MAX_REBUILD_HP,
    MAX_REBUILD_SKILLS,
    ASIChoice,
    ASIIncreaseItem,
    BackgroundChange,
    CharacterASIChoiceResponse,
    CharacterRebuildRequest,
    FeatChoice,
    LevelUpRequest,
    SubclassChange,
    SubraceChange,
)


@pytest.mark.unit
class TestBackgroundChange:
    def test_accepts_background_id(self):
        assert BackgroundChange(background_id=5).background_id == 5

    def test_missing_background_id_is_rejected(self):
        with pytest.raises(ValidationError):
            BackgroundChange()


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


@pytest.mark.unit
class TestInputBounds:
    def test_database_ids_above_int32_are_rejected(self):
        with pytest.raises(ValidationError):
            BackgroundChange(background_id=2**31)

        with pytest.raises(ValidationError):
            FeatChoice(feat_id=2**31)

    def test_non_positive_ids_are_rejected(self):
        with pytest.raises(ValidationError):
            FeatChoice(feat_id=0)

        with pytest.raises(ValidationError):
            SubclassChange(subclass_id=-1)

    def test_clearing_subclass_or_subrace_with_null_is_still_allowed(self):
        assert SubclassChange(subclass_id=None).subclass_id is None
        assert SubraceChange(subrace_id=None).subrace_id is None

    def test_hit_points_gained_has_an_upper_bound(self):
        assert LevelUpRequest(hit_points_gained=MAX_HIT_POINTS_GAINED).hit_points_gained == MAX_HIT_POINTS_GAINED
        with pytest.raises(ValidationError):
            LevelUpRequest(hit_points_gained=MAX_HIT_POINTS_GAINED + 1)

    def test_feature_choices_list_is_bounded(self):
        answer = {"feature_id": 1, "choice_group_id": 1, "choice_option_id": 1}

        assert (
            len(LevelUpRequest(feature_choices=[answer] * MAX_FEATURE_CHOICES).feature_choices) == MAX_FEATURE_CHOICES
        )
        with pytest.raises(ValidationError):
            LevelUpRequest(feature_choices=[answer] * (MAX_FEATURE_CHOICES + 1))

    def test_rebuild_lists_and_hp_are_bounded(self):
        build = {
            "class_id": 1,
            "race_id": 1,
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
            "max_hp": 10,
        }

        assert CharacterRebuildRequest(**build).asi_choices == []
        with pytest.raises(ValidationError):
            CharacterRebuildRequest(**{**build, "max_hp": MAX_REBUILD_HP + 1})
        with pytest.raises(ValidationError):
            CharacterRebuildRequest(**{**build, "skill_ids": list(range(1, MAX_REBUILD_SKILLS + 2))})
