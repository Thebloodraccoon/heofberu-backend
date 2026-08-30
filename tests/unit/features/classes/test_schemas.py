"""Unit tests for class schema validators."""

from pydantic import ValidationError
import pytest

from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
)


@pytest.mark.unit
class TestClassCreateValidators:
    def test_non_caster_is_valid(self):
        character_class = ClassCreate(name="Fighter", hit_dice="D10", spellcasting_ability=None)

        assert character_class.spellcasting_ability is None

    def test_caster_is_valid(self):
        character_class = ClassCreate(name="Wizard", hit_dice="D6", spellcasting_ability="INT")

        assert character_class.spellcasting_ability == "INT"

    def test_duplicate_saving_throws_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate saving throws"):
            ClassCreate(
                name="Dup",
                hit_dice="D8",
                spellcasting_ability=None,
                saving_throws=["STR", "STR"],
            )


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
