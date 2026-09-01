"""Eligibility rules for a character learning a spell."""

from app.features.characters.spells.exceptions import (
    NoSpellSlotAvailableException,
    SpellNotAvailableToCharacterException,
)
from app.features.characters.spells.repository import (
    CharacterSpellRepository,
    CharacterSpellSlotRepository,
)
from app.models import Character, Spell


class CharacterSpellEligibilityChecker:
    """
    Pure(ish) rule-checker for whether a character may learn a spell:
    the class/race restriction check and the spell-slot capacity check,
    extracted out of ``CharacterSpellService`` for testability. Takes the
    two spell sub-repositories since capacity needs both slots and known
    spells, but has no access-control or persistence responsibility.
    """

    def __init__(
        self,
        slot_repository: CharacterSpellSlotRepository,
        known_spell_repository: CharacterSpellRepository,
    ):
        """Create the eligibility checker with its two repositories."""

        self.slot_repository = slot_repository
        self.known_spell_repository = known_spell_repository

    async def check(self, character: Character, spell: Spell) -> None:
        """
        Raise the appropriate exception if ``character`` may not learn
        ``spell``: the class/race restriction check first, then the
        slot-capacity check — both must pass.
        """

        self._check_spell_available_to_character(character, spell)
        await self._check_slot_available(character.id, spell)

    def _check_spell_available_to_character(self, character: Character, spell: Spell) -> None:
        """
        Raise ``SpellNotAvailableToCharacterException`` unless ``spell`` is
        available on ALL four dimensions (class, subclass, race, subrace):
        an empty ``available_*`` list never excludes, a non-empty one
        requires membership, and a missing subclass/subrace fails any
        dimension restricted to at least one entry.
        """

        class_ok = not spell.available_classes or any(c.id == character.class_id for c in spell.available_classes)
        subclass_ok = not spell.available_subclasses or (
            character.subclass_id is not None and any(s.id == character.subclass_id for s in spell.available_subclasses)
        )
        race_ok = not spell.available_races or (
            character.race_id is not None and any(r.id == character.race_id for r in spell.available_races)
        )
        subrace_ok = not spell.available_subraces or (
            character.subrace_id is not None and any(sr.id == character.subrace_id for sr in spell.available_subraces)
        )

        if not (class_ok and subclass_ok and race_ok and subrace_ok):
            raise SpellNotAvailableToCharacterException(character_id=character.id, spell_id=spell.id)

    async def _check_slot_available(self, character_id: int, spell: Spell) -> None:
        """
        Raise ``NoSpellSlotAvailableException`` if the character already
        knows as many spells of ``spell.level`` as slots of that level
        (``total`` minus known-at-level; a missing slot entry = 0).
        """

        slot = await self.slot_repository.get_spell_slot(character_id, spell.level)
        total_slots = slot.total if slot is not None else 0

        known_at_level = await self.known_spell_repository.count_known_spells_at_level(character_id, spell.level)

        if known_at_level >= total_slots:
            raise NoSpellSlotAvailableException(character_id=character_id, level=spell.level)
