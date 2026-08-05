"""Unit tests for class schema validators."""

from pydantic import ValidationError
import pytest

from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    ClassUpdate,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
)


@pytest.mark.unit
class TestClassCreateValidators:
    def test_spellcasting_ability_must_be_primary(self):
        with pytest.raises(ValidationError, match="must also appear in primary_abilities"):
            ClassCreate(name="Bad Caster", hit_dice="D8", spellcasting_ability="CHA")

    def test_non_caster_is_valid(self):
        character_class = ClassCreate(name="Fighter", hit_dice="D10", spellcasting_ability=None)

        assert character_class.spellcasting_ability is None

    def test_duplicate_primary_abilities_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate primary abilities"):
            ClassCreate(
                name="Dup",
                hit_dice="D8",
                spellcasting_ability="INT",
                primary_abilities=["INT", "INT"],
            )

    def test_duplicate_saving_throws_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate saving throws"):
            ClassCreate(
                name="Dup",
                hit_dice="D8",
                spellcasting_ability=None,
                saving_throws=["STR", "STR"],
            )


@pytest.mark.unit
class TestClassUpdateValidators:
    def test_both_fields_set_mismatched_rejected(self):
        with pytest.raises(ValidationError, match="must also appear in primary_abilities"):
            ClassUpdate(spellcasting_ability="CHA", primary_abilities=["INT"])

    def test_duplicate_primary_abilities_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate primary abilities"):
            ClassUpdate(primary_abilities=["INT", "INT"])


@pytest.mark.unit
class TestSpellSlotProgressionValidators:
    def test_duplicate_spell_levels_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate spell_level"):
            SpellSlotProgressionUpdate(
                slots=[{"spell_level": "LEVEL_1", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 3}]
            )


@pytest.mark.unit
class TestListUpdateValidators:
    def test_duplicate_saving_throws_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate saving throws"):
            SavingThrowsUpdate(saving_throws=["STR", "STR"])

    def test_duplicate_skill_ids_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate skill IDs"):
            AvailableSkillsUpdate(skill_ids=[1, 1])
