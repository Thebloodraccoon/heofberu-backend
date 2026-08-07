"""Unit tests for character schema validators introduced in the refactor."""

from pydantic import ValidationError
import pytest

from app.features.characters.core.schemas import RestRequest
from app.features.characters.schemas import CharacterUpdate
from app.features.characters.spells.schemas import SpellSlotUpdate


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
class TestSpellSlotUpdate:
    def test_accepts_known_level(self):
        update = SpellSlotUpdate(level="LEVEL_3", used=1)

        assert update.level.value == "LEVEL_3"

    def test_accepts_cantrip_level(self):
        assert SpellSlotUpdate(level="CANTRIP").level.value == "CANTRIP"

    def test_rejects_unknown_level(self):
        with pytest.raises(ValidationError):
            SpellSlotUpdate(level="LEVEL_10")

    def test_rejects_non_level_string(self):
        with pytest.raises(ValidationError):
            SpellSlotUpdate(level="all")

    def test_used_is_optional(self):
        assert SpellSlotUpdate(level="LEVEL_1").used is None

    def test_rejects_total_field(self):
        """`total` is not client-settable — it always comes from class/level progression."""
        with pytest.raises(ValidationError):
            SpellSlotUpdate(level="LEVEL_1", total=2)


@pytest.mark.unit
class TestCharacterUpdate:
    def test_accepts_subclass(self):
        assert CharacterUpdate(subclass="Arcane Trickster").subclass == "Arcane Trickster"

    def test_subclass_defaults_to_none(self):
        assert CharacterUpdate().subclass is None
