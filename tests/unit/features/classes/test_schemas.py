"""Unit tests for the class schemas: duplicates, null/length/range guards, image_url."""

from pydantic import ValidationError
import pytest

from app.constants import AbilityScore
from app.features.classes.crud.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.classes.proficiencies.schemas import (
    ArmorProficienciesUpdate,
    SavingThrowsUpdate,
    WeaponProficienciesUpdate,
)
from app.features.classes.progression.schemas import SpellSlotProgressionUpdate
from app.features.classes.skills.schemas import AvailableSkillsUpdate


def make_create(**overrides) -> ClassCreate:
    payload = {"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None, **overrides}
    return ClassCreate(**payload)


@pytest.mark.unit
class TestClassCreate:
    def test_non_caster_is_valid(self):
        assert make_create().spellcasting_ability is None

    def test_caster_is_valid(self):
        assert make_create(name="Wizard", hit_dice="D6", spellcasting_ability="INT").spellcasting_ability == "INT"

    @pytest.mark.parametrize("name", ["", "x" * 101])
    def test_name_length_is_bounded(self, name):
        with pytest.raises(ValidationError):
            make_create(name=name)

    @pytest.mark.parametrize("count", [-1, 21])
    def test_skill_choice_count_range(self, count):
        with pytest.raises(ValidationError):
            make_create(skill_choice_count=count)

    def test_description_length_is_bounded(self):
        with pytest.raises(ValidationError):
            make_create(description="x" * 10_001)

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "/relative.png", "ftp://host/a.png"])
    def test_image_url_must_be_an_absolute_http_url(self, url):
        with pytest.raises(ValidationError):
            make_create(image_url=url)

    def test_image_url_length_is_bounded(self):
        with pytest.raises(ValidationError):
            make_create(image_url="https://example.com/" + "a" * 520)

    def test_valid_image_url_is_kept(self):
        assert make_create(image_url="https://cdn.example.com/c.png").image_url == "https://cdn.example.com/c.png"


@pytest.mark.unit
class TestClassUpdate:
    @pytest.mark.parametrize("field", ["name", "hit_dice", "skill_choice_count", "description"])
    def test_explicit_null_is_rejected_for_required_columns(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            ClassUpdate(**{field: None})

    def test_spellcasting_ability_may_be_cleared(self):
        update = ClassUpdate(spellcasting_ability=None)

        assert update.model_dump(exclude_unset=True) == {"spellcasting_ability": None}

    def test_omitted_fields_stay_unset(self):
        assert ClassUpdate(description="x").model_dump(exclude_unset=True) == {"description": "x"}

    def test_range_and_length_guards(self):
        with pytest.raises(ValidationError):
            ClassUpdate(skill_choice_count=-1)
        with pytest.raises(ValidationError):
            ClassUpdate(name="")
        with pytest.raises(ValidationError):
            ClassUpdate(name="x" * 101)

    def test_duplicate_saving_throws_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate saving throws"):
            ClassUpdate(saving_throws=[AbilityScore.STR, AbilityScore.STR])


@pytest.mark.unit
class TestListUpdates:
    def test_duplicate_saving_throws_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate saving throws"):
            SavingThrowsUpdate(saving_throws=["STR", "STR"])

    def test_duplicate_armor_proficiencies_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate armor proficiencies"):
            ArmorProficienciesUpdate(armor_proficiencies=["LIGHT", "LIGHT"])

    def test_duplicate_weapon_proficiencies_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate weapon proficiencies"):
            WeaponProficienciesUpdate(weapon_proficiencies=["SIMPLE", "SIMPLE"])

    def test_duplicate_skill_ids_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate skill IDs"):
            AvailableSkillsUpdate(skill_ids=[1, 1])

    def test_skill_id_list_is_bounded(self):
        with pytest.raises(ValidationError):
            AvailableSkillsUpdate(skill_ids=list(range(1, 102)))

    def test_duplicate_spell_levels_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate spell_level"):
            SpellSlotProgressionUpdate(
                slots=[{"spell_level": "LEVEL_1", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 3}]
            )

    def test_negative_slots_rejected(self):
        with pytest.raises(ValidationError):
            SpellSlotProgressionUpdate(slots=[{"spell_level": "LEVEL_1", "slots": -1}])


@pytest.mark.unit
class TestClassResponse:
    def test_response_does_not_apply_create_constraints_to_stored_rows(self):
        response = ClassResponse.model_validate(
            {"id": 1, "name": "x" * 150, "hit_dice": "D8", "spellcasting_ability": None, "image_url": "legacy"}
        )

        assert response.image_url == "legacy"
