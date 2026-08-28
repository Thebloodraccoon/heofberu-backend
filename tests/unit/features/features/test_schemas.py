"""Unit tests for feature schema validators."""

from pydantic import ValidationError
import pytest

from app.features.features.crud.schemas import FeatureCreate


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
