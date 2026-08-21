"""Unit tests for character schema validators introduced in the refactor."""

from pydantic import ValidationError
import pytest

from app.features.characters.crud.schemas import RestRequest
from app.features.characters.crud.service import CharacterService
from app.features.characters.schemas import (
    AbilityScoresResponse,
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
)
from app.features.characters.spells.schemas import SpellSlotResponse


@pytest.mark.unit
class TestRestRequest:
    def test_accepts_short_rest(self):
        assert RestRequest(type="short").type == "short"

    def test_accepts_long_rest(self):
        assert RestRequest(type="long").type == "long"

    def test_rejects_unknown_rest_type(self):
        with pytest.raises(ValidationError):
            RestRequest(type="overnight")

    def test_rejects_missing_type(self):
        with pytest.raises(ValidationError):
            RestRequest()


@pytest.mark.unit
class TestSpellSlotResponse:
    def test_exposes_only_level_and_total(self):
        """Slots are class-derived capacity — there is no `used` tracking."""
        slot = SpellSlotResponse.model_validate({"spell_level": "LEVEL_1", "total": 2, "used": 1})

        assert slot.spell_level == "LEVEL_1"
        assert slot.total == 2
        assert not hasattr(slot, "used")


@pytest.mark.unit
class TestCharacterUpdate:
    def test_subclass_is_not_a_patchable_field(self):
        """subclass is fixed at creation and changed via the progression endpoint, not PATCH."""
        assert "subclass" not in CharacterUpdate.model_fields
        assert "subclass_id" not in CharacterUpdate.model_fields

    def test_extra_subclass_fields_are_ignored(self):
        update = CharacterUpdate(name="Renamed", subclass_id=999, subclass="Arcane Trickster")

        assert update.name == "Renamed"

    def test_armor_class_and_shield_are_patchable(self):
        update = CharacterUpdate(armor_class=17, shield=2)

        assert update.armor_class == 17
        assert update.shield == 2

    def test_removed_model_fields_are_gone(self):
        """Fields dropped from the Character model must not linger on the update schema."""
        for field in (
            "image_path",
            "traits",
            "proficiencies",
            "initiative_bonus",
            "passive_perception_bonus",
            "has_jack_of_all_trades",
            "spell_ability",
            "spell_dc_misc_bonus",
            "spell_attack_misc_bonus",
        ):
            assert field not in CharacterUpdate.model_fields, f"'{field}' should have been removed"

    def test_max_hp_is_not_player_patchable(self):
        """max_hp changes go through the GM-only panel endpoint, not the plain PATCH."""
        assert "max_hp" not in CharacterUpdate.model_fields


@pytest.mark.unit
class TestCharacterCreate:
    def _payload(self, **overrides):
        payload = {"name": "Grog", "class_id": 1}
        payload.update(overrides)
        return payload

    def test_level_is_not_client_settable(self):
        """Every character starts at level 1; level is not part of the create payload."""
        assert "level" not in CharacterCreate.model_fields

    def test_max_hp_is_not_client_settable(self):
        """Level-1 HP is fixed server-side (hit die + CON mod); max_hp is not payload input."""
        assert "max_hp" not in CharacterCreate.model_fields

    def test_current_hp_and_temp_hp_are_not_client_settable(self):
        """HP is fully server-derived at creation."""
        assert "current_hp" not in CharacterCreate.model_fields
        assert "temp_hp" not in CharacterCreate.model_fields

    def test_skill_ids_default_to_empty(self):
        create = CharacterCreate(**self._payload())

        assert create.skill_ids == []

    def test_duplicate_skill_ids_rejected(self):
        with pytest.raises(ValidationError):
            CharacterCreate(**self._payload(skill_ids=[1, 2, 2]))

    def test_unique_skill_ids_accepted(self):
        create = CharacterCreate(**self._payload(skill_ids=[1, 2]))

        assert create.skill_ids == [1, 2]

    def test_unknown_fields_are_forbidden(self):
        """Stale clients sending removed fields (e.g. level/max_hp) get a loud 422-equivalent."""
        with pytest.raises(ValidationError):
            CharacterCreate(**self._payload(level=5))

        with pytest.raises(ValidationError):
            CharacterCreate(**self._payload(max_hp=22))


@pytest.mark.unit
class TestApplyHpDelta:
    """The pure 5e damage/healing resolution used by PATCH /{id}/hp."""

    def test_healing_adds_to_current_only(self):
        assert CharacterService._apply_hp_delta(current_hp=10, temp_hp=5, delta=4) == (14, 5)

    def test_damage_absorbed_by_temp_first(self):
        assert CharacterService._apply_hp_delta(current_hp=20, temp_hp=8, delta=-5) == (20, 3)

    def test_damage_overflow_hits_current(self):
        assert CharacterService._apply_hp_delta(current_hp=20, temp_hp=3, delta=-7) == (16, 0)

    def test_damage_without_temp(self):
        assert CharacterService._apply_hp_delta(current_hp=12, temp_hp=0, delta=-15) == (-3, 0)


@pytest.mark.unit
class TestCharacterResponseAbilityScoreExclusion:
    def test_raw_ability_scores_excluded_from_serialization(self):
        """Raw base scores (strength..charisma) must not appear in JSON output."""
        data = {
            "id": 1,
            "owner_id": 1,
            "name": "Grog",
            "class_id": 1,
            "race_id": 1,
            "background_id": 1,
            "level": 5,
            "current_hp": 20,
            "max_hp": 22,
            "temp_hp": 0,
            "strength": 14,
            "dexterity": 10,
            "constitution": 12,
            "intelligence": 8,
            "wisdom": 9,
            "charisma": 11,
        }
        response = CharacterResponse.model_validate(data)
        dumped = response.model_dump()

        for raw_field in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
            assert raw_field not in dumped, f"Raw field '{raw_field}' should not appear in serialized response"

    def test_effective_ability_scores_present(self):
        """Effective totals (ability_scores.*) must be present in the response."""
        data = {
            "id": 1,
            "owner_id": 1,
            "name": "Grog",
            "class_id": 1,
            "race_id": 1,
            "background_id": 1,
            "level": 5,
            "current_hp": 20,
            "max_hp": 22,
            "temp_hp": 0,
            "strength": 14,
            "dexterity": 10,
            "constitution": 12,
            "intelligence": 8,
            "wisdom": 9,
            "charisma": 11,
        }
        response = CharacterResponse.model_validate(data)
        response.ability_scores = AbilityScoresResponse(
            strength_total=16,
            dexterity_total=10,
            constitution_total=12,
            intelligence_total=8,
            wisdom_total=9,
            charisma_total=11,
        )
        dumped = response.model_dump()

        assert "ability_scores" in dumped
        assert dumped["ability_scores"]["strength_total"] == 16
