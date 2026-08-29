"""Unit tests for feature schema validators."""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from app.features.features.ability_increases.schemas import AbilityIncreaseItem
from app.features.features.crud.schemas import FeatureCreate, FeatureResponse, NestedFeatureResponse


@pytest.mark.unit
class TestFeatureValidators:
    def test_class_feature_requires_class_id(self):
        with pytest.raises(ValidationError, match="requires 'class_id' to be set"):
            FeatureCreate(name="Extra Attack", source_type="CLASS", level=1)

    def test_subclass_feature_requires_subclass_id(self):
        with pytest.raises(ValidationError, match="requires 'subclass_id' to be set"):
            FeatureCreate(name="Channel Divinity", source_type="SUBCLASS", level=2)

    def test_other_feature_rejects_foreign_keys(self):
        with pytest.raises(ValidationError, match="must not set 'race_id'"):
            FeatureCreate(name="Bad", source_type="OTHER", race_id=1)

    def test_class_feature_requires_level(self):
        with pytest.raises(ValidationError, match="requires 'level' to be set"):
            FeatureCreate(name="Extra Attack", source_type="CLASS", class_id=1)

    def test_class_feature_level_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="must be between 1 and 20"):
            FeatureCreate(name="Extra Attack", source_type="CLASS", class_id=1, level=25)

    def test_race_feature_allows_optional_level(self):
        feature = FeatureCreate(name="Keen Senses", source_type="RACE", race_id=1, level=5)
        assert feature.level == 5

        no_level = FeatureCreate(name="Keen Senses", source_type="RACE", race_id=1)
        assert no_level.level is None

    def test_other_feature_allows_level(self):
        feature = FeatureCreate(name="Aether Gift", source_type="OTHER", level=3)
        assert feature.level == 3


@pytest.mark.unit
class TestAbilityIncreaseItemCap:
    def test_new_cap_at_twenty_is_allowed(self):
        assert AbilityIncreaseItem(ability="STR", amount=2, new_cap=20).new_cap == 20

    def test_new_cap_at_thirty_is_allowed(self):
        assert AbilityIncreaseItem(ability="STR", amount=4, new_cap=30).new_cap == 30

    def test_new_cap_above_thirty_rejected(self):
        with pytest.raises(ValidationError, match="new_cap"):
            AbilityIncreaseItem(ability="STR", amount=4, new_cap=31)

    def test_new_cap_below_twenty_rejected(self):
        with pytest.raises(ValidationError, match="new_cap"):
            AbilityIncreaseItem(ability="STR", amount=1, new_cap=19)

    def test_new_cap_omitted_is_allowed(self):
        assert AbilityIncreaseItem(ability="STR", amount=2).new_cap is None


@pytest.mark.unit
class TestFeatureResponsesEmbedAbilityIncreases:
    def test_feature_response_embeds_ability_increases(self):
        source = type(
            "Feature",
            (),
            {
                "id": 1,
                "name": "Primal Champion",
                "source_type": "OTHER",
                "class_id": None,
                "subclass_id": None,
                "race_id": None,
                "subrace_id": None,
                "background_id": None,
                "level": None,
                "description": "",
                "ability_increases": [
                    AbilityIncreaseItem(ability="STR", amount=4, new_cap=30),
                ],
            },
        )()

        response = FeatureResponse.model_validate(source)

        assert response.ability_increases[0].ability.value == "STR"
        assert response.ability_increases[0].new_cap == 30

    def test_nested_feature_response_embeds_ability_increases(self):
        source = type(
            "Feature",
            (),
            {
                "id": 7,
                "name": "Keen Senses",
                "description": "",
                "level": None,
                "ability_increases": [
                    AbilityIncreaseItem(ability="WIS", amount=1, new_cap=None),
                ],
            },
        )()

        response = NestedFeatureResponse.model_validate(source)

        assert response.ability_increases[0].ability.value == "WIS"

    def test_missing_ability_increases_defaults_to_empty(self):
        source = SimpleNamespace(
            id=1,
            name="Plain",
            description="",
            level=None,
        )

        assert NestedFeatureResponse.model_validate(source).ability_increases == []
