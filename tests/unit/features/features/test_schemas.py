"""Unit tests for feature schema validators."""

from pydantic import ValidationError
import pytest

from app.features.features.schemas import FeatureCreate


@pytest.mark.unit
class TestFeatureValidators:
    def test_class_feature_requires_class_id(self):
        with pytest.raises(ValidationError, match="requires 'class_id' to be set"):
            FeatureCreate(name="Extra Attack", source_type="CLASS")

    def test_other_feature_rejects_foreign_keys(self):
        with pytest.raises(ValidationError, match="must not set 'race_id'"):
            FeatureCreate(name="Bad", source_type="OTHER", race_id=1)

    def test_level_only_for_class_or_subclass(self):
        with pytest.raises(ValidationError, match="only meaningful when source_type is CLASS or SUBCLASS"):
            FeatureCreate(name="Bad", source_type="RACE", race_id=1, level=5)
