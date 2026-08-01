from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.characters.spells.exceptions import (
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
    InvalidSpellSlotUsageException,
)
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellPrepareUpdate,
    CharacterSpellResponse,
    SpellSlotResponse,
    SpellSlotUpdate,
)
from app.features.spells.exceptions import SpellNotFoundException
from app.features.spells.repository import SpellRepository
from app.features.users.schemas import UserResponse
from app.models.character_spell_model import CharacterSpell


class CharacterSpellService:
    """
    Spell slots and known spells for a character.

    Two related but distinct sub-domains that share this service since both
    live under "what a character can cast": slot totals/usage per level, and
    the list of spells a character knows (with prepared status).
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
        """List all spells known by the character, with prepared status."""

        get_character_for_user(self.repository, character_id, current_user)

        known_spells = self.repository.get_known_spells(character_id)
        return [CharacterSpellResponse.model_validate(cs) for cs in known_spells]

    def add_known_spell(
        self, character_id: int, data: CharacterSpellAdd, current_user: UserResponse
    ) -> CharacterSpellResponse:
        """
        Add a spell to the character's known spells.

        Raises ``SpellNotFoundException`` if the spell doesn't exist, or
        ``CharacterSpellAlreadyKnownException`` if the character already
        knows it.
        """

        get_character_for_user(self.repository, character_id, current_user)

        spell = self.spell_repository.get_by_id(data.spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=data.spell_id)

        existing = self.repository.get_known_spell(character_id, data.spell_id)
        if existing:
            raise CharacterSpellAlreadyKnownException(character_id=character_id, spell_id=data.spell_id)

        character_spell = self.repository.add_known_spell(character_id, data.spell_id)
        return CharacterSpellResponse.model_validate(character_spell)

    def remove_known_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> bool:
        """Remove a spell from the character's known spells."""

        get_character_for_user(self.repository, character_id, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        return self.repository.remove_known_spell(character_spell)

    def set_spell_prepared(
        self,
        character_id: int,
        spell_id: int,
        data: CharacterSpellPrepareUpdate,
        current_user: UserResponse,
    ) -> CharacterSpellResponse:
        """Toggle whether a known spell is currently prepared."""

        get_character_for_user(self.repository, character_id, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        updated = self.repository.set_spell_prepared(character_spell, data.is_prepared)
        return CharacterSpellResponse.model_validate(updated)

    def _get_known_spell_or_404(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Fetch a known-spell entry, or raise ``CharacterSpellNotFoundException``."""

        character_spell = self.repository.get_known_spell(character_id, spell_id)
        if not character_spell:
            raise CharacterSpellNotFoundException(character_id=character_id, spell_id=spell_id)

        return character_spell
