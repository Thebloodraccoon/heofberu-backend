"""Unit tests for feature schema validators."""

from pydantic import ValidationError
import pytest

from app.features.features.crud.schemas import FeatureCreate, StandaloneFeatureCreate


@pytest.mark.unit
class TestFeatureValidators:
    def test_class_feature_requires_class_id(self):
        with pytest.raises(ValidationError, match="requires 'class_id' to be set"):
            FeatureCreate(name="Extra Attack", source_type="CLASS")

    def test_other_feature_rejects_foreign_keys(self):
        with pytest.raises(ValidationError, match="must not set 'race_id'"):
            FeatureCreate(name="Bad", source_type="OTHER", race_id=1)

    def test_level_only_for_class_or_subclass(self):
        with pytest.raises(ValidationError, match="only meaningful when source_type is CLASS, SUBCLASS or OTHER"):
            FeatureCreate(name="Bad", source_type="RACE", race_id=1, level=5)

    def test_other_feature_allows_level(self):
        feature = FeatureCreate(name="Aether Gift", source_type="OTHER", level=3)
        assert feature.level == 3


@pytest.mark.unit
class TestStandaloneFeatureValidators:
    def test_standalone_create_defaults_to_other(self):
        feature = StandaloneFeatureCreate(name="Custom Gift")
        assert feature.source_type == "OTHER"

    def test_standalone_create_rejects_non_other_source(self):
        with pytest.raises(ValidationError, match="created through their parent entities"):
            StandaloneFeatureCreate(name="Extra Attack", source_type="CLASS")

    def test_standalone_create_rejects_removed_feat_fk(self):
        with pytest.raises(ValidationError, match="feat_id"):
            StandaloneFeatureCreate(name="Bad", source_type="OTHER", feat_id=1)
