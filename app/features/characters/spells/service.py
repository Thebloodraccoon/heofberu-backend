from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.characters.spells.exceptions import (
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
    InvalidSpellSlotUsageException,
    NoSpellSlotAvailableException,
    SpellNotAvailableToCharacterException,
)
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellResponse,
    SpellSlotResponse,
    SpellSlotUpdate,
)
from app.features.spells.exceptions import SpellNotFoundException
from app.features.spells.repository import SpellRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character
from app.models.character_spell_model import CharacterSpell
from app.models.spell_model import Spell


class CharacterSpellService:
    """
    Spell slots and known spells for a character.

    Two related but distinct sub-domains that share this service since both
    live under "what a character can cast": slot totals/usage per level, and
    the list of spells a character knows.

    There is no separate "prepared" state — knowing a spell IS having it
    ready to cast. Choosing a spell (``add_known_spell``) is capped by the
    character's spell slot totals: a character may know at most as many
    spells of a given level as they have ``CharacterSpellSlot.total`` at
    that level (see ``_check_slot_available``). To swap a known spell for
    a different one, remove the old one and add the new one — that frees
    up the slot it was occupying. Nothing about knowing a spell resets on
    rest; only ``CharacterSpellSlot.used`` (actual casting) does, via
    ``CharacterService.rest``, and how that's tracked day-to-day is left
    entirely to the GM.

    ``add_known_spell`` also checks the spell's ``available_classes``/
    ``available_races`` restrictions (if any) against the character's
    class/race — see ``_check_spell_available_to_character``.
    """

    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
        self.spell_repository = SpellRepository(db)

    def get_spell_slots(self, character_id: int, current_user: UserResponse) -> list[SpellSlotResponse]:
        """Return all spell slot entries (by level) for a character."""

        get_character_for_user(self.repository, character_id, current_user)

        slots = self.repository.get_all_spell_slots(character_id)
        return [SpellSlotResponse.model_validate(slot) for slot in slots]

    def update_spell_slot(
        self, character_id: int, data: SpellSlotUpdate, current_user: UserResponse
    ) -> SpellSlotResponse:
        """
        Spend or restore a spell slot at a given level.

        If no entry exists yet for this level, one is created — this also
        covers initially granting a character's slots (e.g. total=4, used=0).
        """

        get_character_for_user(self.repository, character_id, current_user)

        existing = self.repository.get_spell_slot(character_id, data.level)
        current_total = existing.total if existing else 0
        current_used = existing.used if existing else 0

        new_total = data.total if data.total is not None else current_total
        new_used = data.used if data.used is not None else current_used

        if new_used < 0 or new_used > new_total:
            raise InvalidSpellSlotUsageException()

        slot = self.repository.upsert_spell_slot(character_id, data.level, new_total, new_used)
        return SpellSlotResponse.model_validate(slot)

    def get_known_spells(self, character_id: int, current_user: UserResponse) -> list[CharacterSpellResponse]:
        """List all spells known by the character."""

        get_character_for_user(self.repository, character_id, current_user)

        known_spells = self.repository.get_known_spells(character_id)
        return [CharacterSpellResponse.model_validate(cs) for cs in known_spells]

    def add_known_spell(
        self, character_id: int, data: CharacterSpellAdd, current_user: UserResponse
    ) -> CharacterSpellResponse:
        """
        Add a spell to the character's known spells.

        Raises ``SpellNotFoundException`` if the spell doesn't exist,
        ``CharacterSpellAlreadyKnownException`` if the character already
        knows it, ``SpellNotAvailableToCharacterException`` if the spell's
        class/race restrictions exclude this character, or
        ``NoSpellSlotAvailableException`` if the character already knows
        as many spells of this level as they have slots for — remove one
        first to make room.
        """

        character = get_character_for_user(self.repository, character_id, current_user)

        spell = self.spell_repository.get_by_id(data.spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=data.spell_id)

        existing = self.repository.get_known_spell(character_id, data.spell_id)
        if existing:
            raise CharacterSpellAlreadyKnownException(character_id=character_id, spell_id=data.spell_id)

        self._check_spell_available_to_character(character, spell)
        self._check_slot_available(character_id, spell)

        character_spell = self.repository.add_known_spell(character_id, data.spell_id)
        return CharacterSpellResponse.model_validate(character_spell)

    def remove_known_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> bool:
        """Remove a spell from the character's known spells, freeing up its slot."""

        get_character_for_user(self.repository, character_id, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        return self.repository.remove_known_spell(character_spell)

    def _get_known_spell_or_404(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Fetch a known-spell entry, or raise ``CharacterSpellNotFoundException``."""

        character_spell = self.repository.get_known_spell(character_id, spell_id)
        if not character_spell:
            raise CharacterSpellNotFoundException(character_id=character_id, spell_id=spell_id)

        return character_spell

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

        slot = self.repository.get_spell_slot(character_id, spell.level)
        total_slots = slot.total if slot is not None else 0

        known_at_level = self.repository.count_known_spells_at_level(character_id, spell.level)

        if known_at_level >= total_slots:
            raise NoSpellSlotAvailableException(character_id=character_id, level=spell.level)