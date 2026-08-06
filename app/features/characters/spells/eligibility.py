"""Eligibility rules for a character learning a spell."""

from app.features.characters.spells.exceptions import (
    NoSpellSlotAvailableException,
    SpellNotAvailableToCharacterException,
)
from app.features.characters.spells.repository import (
    CharacterSpellRepository,
    CharacterSpellSlotRepository,
)
from app.models.character_model import Character
from app.models.spell_model import Spell


class CharacterSpellEligibilityChecker:
    """
    Pure(ish) rule-checker for whether a character may learn a given spell.

    Extracted out of ``CharacterSpellService`` so these two rules — class/
    race restriction, and spell-slot capacity — are testable in isolation
    from the service's DB-session wiring, and reusable if more eligibility
    rules are added later (e.g. a cap on total known spells regardless of
    level). Takes the two spell sub-repositories since the slot-capacity
    check needs both existing slots and known-spell counts, but has no
    other service-layer responsibilities (no access control, no
    persistence of the spell itself).
    """

    def __init__(
        self,
        slot_repository: CharacterSpellSlotRepository,
        known_spell_repository: CharacterSpellRepository,
    ):
        self.slot_repository = slot_repository
        self.known_spell_repository = known_spell_repository

    def check(self, character: Character, spell: Spell) -> None:
        """
        Raise the appropriate exception if ``character`` may not learn
        ``spell``. Runs the class/race restriction check first, then the
        slot-capacity check — both must pass for a spell to be learnable.
        """

        self._check_spell_available_to_character(character, spell)
        self._check_slot_available(character.id, spell)

    def _check_spell_available_to_character(self, character: Character, spell: Spell) -> None:
        """
        Raise ``SpellNotAvailableToCharacterException`` unless ``spell`` is
        available to ``character``'s class or race.

        Each dimension (class, race) is independently unrestricted when
        ``spell.available_classes``/``available_races`` is empty. A spell
        is available to the character if it is unrestricted (or matches)
        on *both* dimensions that are actually restricted — i.e. an empty
        list never excludes, a non-empty list requires membership.
        """

        class_ok = not spell.available_classes or any(c.id == character.class_id for c in spell.available_classes)
        race_ok = not spell.available_races or (
            character.race_id is not None and any(r.id == character.race_id for r in spell.available_races)
        )

        if not (class_ok and race_ok):
            raise SpellNotAvailableToCharacterException(character_id=character.id, spell_id=spell.id)

    def _check_slot_available(self, character_id: int, spell: Spell) -> None:
        """
        Raise ``NoSpellSlotAvailableException`` unless the character has a
        free spell slot at ``spell.level`` to know another spell of that
        level. "Free" = ``CharacterSpellSlot.total`` at that level minus
        the number of spells already known at that level. A missing slot
        entry for the level is treated as 0 total slots.
        """

        slot = self.slot_repository.get_spell_slot(character_id, spell.level)
        total_slots = slot.total if slot is not None else 0

        known_at_level = self.known_spell_repository.count_known_spells_at_level(character_id, spell.level)

        if known_at_level >= total_slots:
            raise NoSpellSlotAvailableException(character_id=character_id, level=spell.level)
