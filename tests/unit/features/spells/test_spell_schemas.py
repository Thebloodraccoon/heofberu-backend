"""Unit tests for spell write schemas: bounds, cross-field rules, PATCH nulls, unknown keys, id de-duplication."""

from pydantic import ValidationError
import pytest

from app.features.spells.availability.schemas import ClassAvailabilityUpdate, RaceAvailabilityUpdate
from app.features.spells.crud.schemas import SpellCreate, SpellUpdate

BASE = {
    "name": "Mage Armor",
    "school": "ABJURATION",
    "level": "LEVEL_1",
    "cast_time": "ACTION",
    "range_type": "TOUCH",
    "duration": "EIGHT_HOURS",
    "description": "text",
}


@pytest.mark.unit
class TestSpellCreateRules:
    def test_minimal_payload_is_valid(self):
        assert SpellCreate(**BASE).name == "Mage Armor"

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            SpellCreate(**BASE, lvl="LEVEL_2")

    @pytest.mark.parametrize("name", ["", "x" * 301])
    def test_name_length_is_bounded(self, name):
        with pytest.raises(ValidationError, match="name"):
            SpellCreate(**{**BASE, "name": name})

    def test_description_length_is_bounded(self):
        with pytest.raises(ValidationError, match="description"):
            SpellCreate(**{**BASE, "description": "x" * 20_001})

    @pytest.mark.parametrize("field", ["damage_dice_count", "healing_dice_count"])
    @pytest.mark.parametrize("value", [0, -1, 101])
    def test_dice_count_is_bounded(self, field, value):
        with pytest.raises(ValidationError, match=field):
            SpellCreate(**{**BASE, field: value, field.replace("count", "type"): "D6"})

    def test_negative_range_value_rejected(self):
        with pytest.raises(ValidationError, match="range_value"):
            SpellCreate(**{**BASE, "range_value": -5})

    @pytest.mark.parametrize("prefix", ["damage", "healing"])
    def test_dice_count_without_type_rejected(self, prefix):
        with pytest.raises(ValidationError, match=f"{prefix}_dice_count and {prefix}_dice_type"):
            SpellCreate(**{**BASE, f"{prefix}_dice_count": 2})

    @pytest.mark.parametrize("prefix", ["damage", "healing"])
    def test_dice_type_without_count_rejected(self, prefix):
        with pytest.raises(ValidationError, match=f"{prefix}_dice_count and {prefix}_dice_type"):
            SpellCreate(**{**BASE, f"{prefix}_dice_type": "D8"})

    def test_dice_count_with_type_is_valid(self):
        spell = SpellCreate(**{**BASE, "damage_dice_count": 2, "damage_dice_type": "D6"})
        assert spell.damage_dice_count == 2

    def test_material_text_requires_the_material_component(self):
        with pytest.raises(ValidationError, match="MATERIAL component"):
            SpellCreate(**{**BASE, "material": "a pinch of dust", "components": ["VERBAL"]})

    def test_consumed_flag_requires_the_material_component(self):
        with pytest.raises(ValidationError, match="MATERIAL component"):
            SpellCreate(**{**BASE, "is_material_consumed": True})

    def test_material_with_material_component_is_valid(self):
        spell = SpellCreate(**{**BASE, "material": "leather", "components": ["MATERIAL"], "is_material_consumed": True})
        assert spell.material == "leather"

    def test_duplicate_components_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate spell component"):
            SpellCreate(**{**BASE, "components": ["VERBAL", "VERBAL"]})

    def test_availability_ids_are_deduplicated_in_order(self):
        spell = SpellCreate(**BASE, available_classes=[3, 1, 3, 1, 2])
        assert spell.available_classes == [3, 1, 2]

    def test_availability_ids_must_be_positive(self):
        with pytest.raises(ValidationError, match="available_races"):
            SpellCreate(**BASE, available_races=[0])

    def test_availability_list_length_is_bounded(self):
        with pytest.raises(ValidationError, match="available_subraces"):
            SpellCreate(**BASE, available_subraces=list(range(1, 502)))


@pytest.mark.unit
class TestSpellUpdateRules:
    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            SpellUpdate(nmae="x")

    @pytest.mark.parametrize(
        "field", ["name", "school", "level", "cast_time", "range_type", "duration", "description", "components"]
    )
    def test_explicit_null_for_a_required_field_rejected(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            SpellUpdate(**{field: None})

    @pytest.mark.parametrize("field", ["is_ritual", "is_concentration", "is_material_consumed"])
    def test_explicit_null_for_a_required_flag_rejected(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            SpellUpdate(**{field: None})

    @pytest.mark.parametrize(
        "field",
        [
            "attack_type",
            "damage_type",
            "damage_dice_count",
            "healing_target",
            "material",
            "higher_levels",
            "range_value",
        ],
    )
    def test_nullable_columns_can_still_be_cleared(self, field):
        update = SpellUpdate(**{field: None})
        assert field in update.model_fields_set

    def test_omitted_fields_are_not_flagged(self):
        assert SpellUpdate(description="new").model_dump(exclude_unset=True) == {"description": "new"}

    def test_name_is_bounded(self):
        with pytest.raises(ValidationError, match="name"):
            SpellUpdate(name="x" * 301)


@pytest.mark.unit
class TestAvailabilityPayloads:
    def test_duplicate_ids_collapse(self):
        assert ClassAvailabilityUpdate(class_ids=[1, 1, 2]).class_ids == [1, 2]

    def test_empty_list_is_allowed(self):
        assert RaceAvailabilityUpdate(race_ids=[]).race_ids == []

    def test_missing_list_rejected(self):
        with pytest.raises(ValidationError, match="class_ids"):
            ClassAvailabilityUpdate()

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ClassAvailabilityUpdate(class_ids=[1], races=[2])

    def test_non_positive_id_rejected(self):
        with pytest.raises(ValidationError, match="class_ids"):
            ClassAvailabilityUpdate(class_ids=[-3])
