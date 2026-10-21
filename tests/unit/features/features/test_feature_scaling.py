"""Unit tests for ``FeatureScaling`` — a feature's one line that grows with the character's level."""

from pydantic import ValidationError
import pytest

from app.features.features.crud.schemas import FeatureCreate, FeatureScaling, FeatureUpdate

SONG_OF_REST = {
    "label": "Доп. хиты",
    "steps": [
        {"level": 13, "value": "1к10"},
        {"level": 2, "value": "1к6"},
        {"level": 17, "value": "1к12"},
        {"level": 9, "value": "1к8"},
    ],
}


@pytest.mark.unit
class TestFeatureScaling:
    def test_steps_come_back_sorted_by_level(self):
        scaling = FeatureScaling.model_validate(SONG_OF_REST)

        assert [step.level for step in scaling.steps] == [2, 9, 13, 17]

    @pytest.mark.parametrize(
        "level,expected",
        [(1, None), (2, "1к6"), (8, "1к6"), (9, "1к8"), (12, "1к8"), (13, "1к10"), (17, "1к12"), (20, "1к12")],
    )
    def test_value_at_takes_the_highest_reached_step(self, level, expected):
        assert FeatureScaling.model_validate(SONG_OF_REST).value_at(level) == expected

    def test_two_steps_on_one_level_are_rejected(self):
        with pytest.raises(ValidationError, match="different levels"):
            FeatureScaling(label="Ци", steps=[{"level": 2, "value": "2"}, {"level": 2, "value": "3"}])

    def test_label_and_values_are_trimmed_and_required(self):
        scaling = FeatureScaling(label="  Ци  ", steps=[{"level": 2, "value": " 2 "}])
        assert scaling.label == "Ци"
        assert scaling.steps[0].value == "2"

        with pytest.raises(ValidationError):
            FeatureScaling(label="   ", steps=[{"level": 2, "value": "2"}])
        with pytest.raises(ValidationError):
            FeatureScaling(label="Ци", steps=[{"level": 2, "value": "  "}])

    def test_needs_at_least_one_step(self):
        with pytest.raises(ValidationError):
            FeatureScaling(label="Ци", steps=[])

    @pytest.mark.parametrize("level", [0, 21])
    def test_step_level_out_of_range_is_rejected(self, level):
        with pytest.raises(ValidationError):
            FeatureScaling(label="Ци", steps=[{"level": level, "value": "2"}])

    def test_feature_create_and_update_carry_scaling(self):
        created = FeatureCreate(name="Песнь отдыха", source_type="CLASS", class_id=1, level=2, scaling=SONG_OF_REST)
        assert created.model_dump()["scaling"]["steps"][0] == {"level": 2, "value": "1к6"}

        cleared = FeatureUpdate(scaling=None)
        assert cleared.model_dump(exclude_unset=True) == {"scaling": None}
