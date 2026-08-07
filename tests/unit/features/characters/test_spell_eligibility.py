"""Unit tests for CharacterSpellEligibilityChecker with fake repositories."""

from types import SimpleNamespace

import pytest

from app.constants import SpellLevel
from app.features.characters.spells.eligibility import CharacterSpellEligibilityChecker
from app.features.characters.spells.exceptions import (
    NoSpellSlotAvailableException,
    SpellNotAvailableToCharacterException,
)
from app.models.character_model import Character
from app.models.spell_model import Spell


class FakeSlotRepository:
    """Stands in for CharacterSpellSlotRepository; ``slot`` may be None."""

    def __init__(self, slot=None):
        self.slot = slot
        self.get_spell_slot_calls = []

    def get_spell_slot(self, character_id, level):
        self.get_spell_slot_calls.append((character_id, level))
        return self.slot


class FakeKnownSpellRepository:
    """Stands in for CharacterSpellRepository's known-spell counting."""

    def __init__(self, known_at_level=0):
        self.known_at_level = known_at_level
        self.count_calls = []

    def count_known_spells_at_level(self, character_id, level):
        self.count_calls.append((character_id, level))
        return self.known_at_level


def make_character(class_id=1, race_id=None) -> Character:
    return Character(id=1, owner_id=1, name="Grog", class_id=class_id, race_id=race_id)


def make_spell(level=SpellLevel.LEVEL_1, available_classes=None, available_races=None) -> Spell:
    return Spell(
        id=1,
        name="Fireball",
        level=level,
        available_classes=available_classes or [],
        available_races=available_races or [],
    )


def make_checker(slot=None, known_at_level=0) -> CharacterSpellEligibilityChecker:
    return CharacterSpellEligibilityChecker(FakeSlotRepository(slot), FakeKnownSpellRepository(known_at_level))


@pytest.mark.unit
class TestCharacterSpellEligibilityChecker:
    def test_unrestricted_spell_with_free_slot_is_learnable(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        checker.check(make_character(), make_spell())

    def test_restricted_by_class_not_matching_raises(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            checker.check(make_character(class_id=1), spell)

    def test_class_restriction_failure_skips_slot_check(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            checker.check(make_character(class_id=1), spell)

        assert checker.slot_repository.get_spell_slot_calls == []

    def test_available_when_class_restriction_matches(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        checker.check(make_character(class_id=2), spell)

    def test_restricted_by_race_and_character_has_no_race_raises(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            checker.check(make_character(race_id=None), spell)

    def test_restricted_by_race_not_matching_raises(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            checker.check(make_character(race_id=8), spell)

    def test_available_when_race_restriction_matches(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        checker.check(make_character(race_id=7), spell)

    def test_race_restriction_alone_does_not_exclude_when_unrestricted(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=1)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        checker.check(make_character(class_id=1, race_id=None), spell)

    def test_free_slot_when_known_below_total(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=1)

        checker.check(make_character(), make_spell())

    def test_full_slot_raises(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=2)

        with pytest.raises(NoSpellSlotAvailableException):
            checker.check(make_character(), make_spell())

    def test_missing_slot_entry_treated_as_zero_total(self):
        checker = make_checker(slot=None, known_at_level=0)

        with pytest.raises(NoSpellSlotAvailableException):
            checker.check(make_character(), make_spell())

    def test_uses_slot_and_known_counts_for_the_spells_level(self):
        slot_repository = FakeSlotRepository(SimpleNamespace(total=1))
        known_spell_repository = FakeKnownSpellRepository(0)
        checker = CharacterSpellEligibilityChecker(slot_repository, known_spell_repository)
        spell = make_spell(level=SpellLevel.LEVEL_3)

        checker.check(make_character(class_id=1), spell)

        assert slot_repository.get_spell_slot_calls == [(1, SpellLevel.LEVEL_3)]
        assert known_spell_repository.count_calls == [(1, SpellLevel.LEVEL_3)]
