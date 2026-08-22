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

    async def get_spell_slot(self, character_id, level):
        self.get_spell_slot_calls.append((character_id, level))
        return self.slot


class FakeKnownSpellRepository:
    """Stands in for CharacterSpellRepository's known-spell counting."""

    def __init__(self, known_at_level=0):
        self.known_at_level = known_at_level
        self.count_calls = []

    async def count_known_spells_at_level(self, character_id, level):
        self.count_calls.append((character_id, level))
        return self.known_at_level


def make_character(class_id=1, race_id=None, subclass_id=None, subrace_id=None) -> Character:
    return Character(
        id=1,
        owner_id=1,
        name="Grog",
        class_id=class_id,
        race_id=race_id,
        subclass_id=subclass_id,
        subrace_id=subrace_id,
    )


def make_spell(
    level=SpellLevel.LEVEL_1,
    available_classes=None,
    available_subclasses=None,
    available_races=None,
    available_subraces=None,
) -> Spell:
    return Spell(
        id=1,
        name="Fireball",
        level=level,
        available_classes=available_classes or [],
        available_subclasses=available_subclasses or [],
        available_races=available_races or [],
        available_subraces=available_subraces or [],
    )


def make_checker(slot=None, known_at_level=0) -> CharacterSpellEligibilityChecker:
    return CharacterSpellEligibilityChecker(FakeSlotRepository(slot), FakeKnownSpellRepository(known_at_level))


@pytest.mark.unit
@pytest.mark.asyncio
class TestCharacterSpellEligibilityChecker:
    async def test_unrestricted_spell_with_free_slot_is_learnable(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(), make_spell())

    async def test_restricted_by_class_not_matching_raises(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(class_id=1), spell)

    async def test_class_restriction_failure_skips_slot_check(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(class_id=1), spell)

        assert checker.slot_repository.get_spell_slot_calls == []

    async def test_available_when_class_restriction_matches(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=2)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(class_id=2), spell)

    async def test_restricted_by_race_and_character_has_no_race_raises(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(race_id=None), spell)

    async def test_restricted_by_race_not_matching_raises(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(race_id=8), spell)

    async def test_available_when_race_restriction_matches(self):
        spell = make_spell(available_races=[SimpleNamespace(id=7)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(race_id=7), spell)

    async def test_race_restriction_alone_does_not_exclude_when_unrestricted(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=1)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(class_id=1, race_id=None), spell)

    async def test_restricted_by_subclass_and_character_has_no_subclass_raises(self):
        spell = make_spell(available_subclasses=[SimpleNamespace(id=5)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(subclass_id=None), spell)

    async def test_restricted_by_subclass_not_matching_raises(self):
        spell = make_spell(available_subclasses=[SimpleNamespace(id=5)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(class_id=1, subclass_id=6), spell)

    async def test_available_when_subclass_restriction_matches(self):
        spell = make_spell(available_subclasses=[SimpleNamespace(id=5)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(class_id=1, subclass_id=5), spell)

    async def test_subclass_restriction_alone_does_not_exclude_when_unrestricted(self):
        spell = make_spell(available_classes=[SimpleNamespace(id=1)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(class_id=1, subclass_id=None), spell)

    async def test_restricted_by_subrace_and_character_has_no_subrace_raises(self):
        spell = make_spell(available_subraces=[SimpleNamespace(id=9)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(race_id=7, subrace_id=None), spell)

    async def test_restricted_by_subrace_not_matching_raises(self):
        spell = make_spell(available_subraces=[SimpleNamespace(id=9)])
        checker = make_checker(slot=SimpleNamespace(total=2))

        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(race_id=7, subrace_id=10), spell)

    async def test_available_when_subrace_restriction_matches(self):
        spell = make_spell(available_subraces=[SimpleNamespace(id=9)])
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        await checker.check(make_character(race_id=7, subrace_id=9), spell)

    async def test_all_four_dimensions_must_pass(self):
        """A spell restricted on all four dimensions only matches a character matching every one."""

        spell = make_spell(
            available_classes=[SimpleNamespace(id=1)],
            available_subclasses=[SimpleNamespace(id=5)],
            available_races=[SimpleNamespace(id=7)],
            available_subraces=[SimpleNamespace(id=9)],
        )
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=0)

        # Matches class but not the subrace — rejected.
        with pytest.raises(SpellNotAvailableToCharacterException):
            await checker.check(make_character(class_id=1, subclass_id=5, race_id=7, subrace_id=None), spell)

        # Matching all four passes.
        await checker.check(make_character(class_id=1, subclass_id=5, race_id=7, subrace_id=9), spell)

    async def test_free_slot_when_known_below_total(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=1)

        await checker.check(make_character(), make_spell())

    async def test_full_slot_raises(self):
        checker = make_checker(slot=SimpleNamespace(total=2), known_at_level=2)

        with pytest.raises(NoSpellSlotAvailableException):
            await checker.check(make_character(), make_spell())

    async def test_missing_slot_entry_treated_as_zero_total(self):
        checker = make_checker(slot=None, known_at_level=0)

        with pytest.raises(NoSpellSlotAvailableException):
            await checker.check(make_character(), make_spell())

    async def test_uses_slot_and_known_counts_for_the_spells_level(self):
        slot_repository = FakeSlotRepository(SimpleNamespace(total=1))
        known_spell_repository = FakeKnownSpellRepository(0)
        checker = CharacterSpellEligibilityChecker(slot_repository, known_spell_repository)
        spell = make_spell(level=SpellLevel.LEVEL_3)

        await checker.check(make_character(class_id=1), spell)

        assert slot_repository.get_spell_slot_calls == [(1, SpellLevel.LEVEL_3)]
        assert known_spell_repository.count_calls == [(1, SpellLevel.LEVEL_3)]
