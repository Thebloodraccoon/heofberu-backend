"""Unit tests for ``FeatureCreate``/``NestedFeatureCreate`` write rules shared by create and PATCH."""

from pydantic import ValidationError
import pytest

from app.features.features.crud.schemas import FeatureCreate, NestedFeatureCreate


@pytest.mark.unit
class TestFeatureCreateWriteRules:
    @pytest.mark.parametrize("level", [0, -5, 21, 999])
    def test_level_outside_range_rejected_for_every_source_type(self, level):
        with pytest.raises(ValidationError, match="must be between 1 and 20"):
            FeatureCreate(name="Keen Senses", source_type="RACE", race_id=1, level=level)

    def test_feat_feature_rejects_level(self):
        with pytest.raises(ValidationError, match="FEAT features do not use 'level'"):
            FeatureCreate(name="Alert", source_type="FEAT", level=4)

    def test_feat_feature_accepts_feat_columns(self):
        feat = FeatureCreate(
            name="Heavy Armor Master",
            source_type="FEAT",
            min_level=4,
            prerequisite_ability="STR",
            prerequisite_minimum_score=13,
            prerequisite_description="Proficiency with heavy armor",
        )
        assert feat.min_level == 4

    @pytest.mark.parametrize(
        "extra",
        [
            {"min_level": 4},
            {"prerequisite_ability": "STR", "prerequisite_minimum_score": 13},
            {"prerequisite_description": "Needs magic"},
        ],
    )
    def test_non_feat_feature_rejects_feat_only_columns(self, extra):
        with pytest.raises(ValidationError, match="only valid for FEAT"):
            FeatureCreate(name="Gift", source_type="OTHER", **extra)

    def test_prerequisite_ability_needs_minimum_score(self):
        with pytest.raises(ValidationError, match="must be set together"):
            FeatureCreate(name="Alert", source_type="FEAT", prerequisite_ability="STR")

    def test_prerequisite_score_needs_ability(self):
        with pytest.raises(ValidationError, match="must be set together"):
            FeatureCreate(name="Alert", source_type="FEAT", prerequisite_minimum_score=13)

    def test_prerequisite_score_is_bounded(self):
        with pytest.raises(ValidationError, match="prerequisite_minimum_score"):
            FeatureCreate(name="Alert", source_type="FEAT", prerequisite_ability="STR", prerequisite_minimum_score=99)

    def test_name_longer_than_column_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            FeatureCreate(name="x" * 201, source_type="OTHER")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            FeatureCreate(name="", source_type="OTHER")

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            FeatureCreate(name="Gift", source_type="OTHER", has_choices=True)


@pytest.mark.unit
class TestNestedFeatureCreate:
    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            NestedFeatureCreate(name="Keen Senses", source_type="RACE")

    def test_level_is_bounded(self):
        with pytest.raises(ValidationError, match="level"):
            NestedFeatureCreate(name="Keen Senses", level=21)

    def test_valid_payload(self):
        assert NestedFeatureCreate(name="Keen Senses", level=3).level == 3
