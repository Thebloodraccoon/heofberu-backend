"""Character spell service: slots and known spells management."""

from sqlalchemy.orm import Session

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.spells.eligibility import CharacterSpellEligibilityChecker
from app.features.characters.spells.exceptions import (
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
    InvalidSpellSlotUsageException,
)
from app.features.characters.spells.repository import (
    CharacterSpellRepository,
    CharacterSpellSlotRepository,
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
from app.models.character_spell_model import CharacterSpell


class CharacterSpellService(CharacterSubDomainService):
    """
    Spell slots and known spells for a character.

    Two related but distinct sub-domains that share this service since both
    live under "what a character can cast": slot totals/usage per level, and
    the list of spells a character knows.

    There is no separate "prepared" state — knowing a spell IS having it
    ready to cast. Choosing a spell (``add_known_spell``) is capped by the
    character's spell slot totals: a character may know at most as many
    spells of a given level as they have ``CharacterSpellSlot.total`` at
    that level — enforced by ``CharacterSpellEligibilityChecker``, not
    inline here (see that class). To swap a known spell for a different
    one, remove the old one and add the new one — that frees up the slot
    it was occupying. Nothing about knowing a spell resets on rest; only
    ``CharacterSpellSlot.used`` (actual casting) does, via
    ``CharacterService.rest``, and how that's tracked day-to-day is left
    entirely to the GM.

    Uses three repositories:
      - the inherited ``CharacterSubDomainService`` — access control only
        (fetching the owning character to check GM/owner permission).
      - ``CharacterSpellSlotRepository`` — the ``character_spell_slots``
        rows (totals/usage per level).
      - ``CharacterSpellRepository`` — the ``character_spells`` known-
        spell rows.
      - ``SpellRepository`` — looking up the reference spell when adding
        a known spell.
    Eligibility rules (class/race restrictions, slot capacity) are
    delegated to ``CharacterSpellEligibilityChecker``.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.character_spell_slot_repository = CharacterSpellSlotRepository(db)
        self.character_spell_repository = CharacterSpellRepository(db)
        self.spell_repository = SpellRepository(db)
        self.eligibility_checker = CharacterSpellEligibilityChecker(
            self.character_spell_slot_repository, self.character_spell_repository
        )

    def get_spell_slots(self, character_id: int, current_user: UserResponse) -> list[SpellSlotResponse]:
        """Return all spell slot entries (by level) for a character."""

        self.get_character_for_user(character_id, current_user)

        slots = self.character_spell_slot_repository.get_all_spell_slots(character_id)
        return [SpellSlotResponse.model_validate(slot) for slot in slots]

    def update_spell_slot(
        self, character_id: int, data: SpellSlotUpdate, current_user: UserResponse
    ) -> SpellSlotResponse:
        """
        Spend or restore a spell slot at a given level.

        If no entry exists yet for this level, one is created — this also
        covers initially granting a character's slots (e.g. total=4, used=0).
        """

        self.get_character_for_user(character_id, current_user)

        level = data.level.value

        existing = self.character_spell_slot_repository.get_spell_slot(character_id, level)
        current_total = existing.total if existing else 0
        current_used = existing.used if existing else 0

        new_total = data.total if data.total is not None else current_total
        new_used = data.used if data.used is not None else current_used

        if new_used < 0 or new_used > new_total:
            raise InvalidSpellSlotUsageException()

        slot = self.character_spell_slot_repository.upsert_spell_slot(character_id, level, new_total, new_used)
        return SpellSlotResponse.model_validate(slot)

    def get_known_spells(self, character_id: int, current_user: UserResponse) -> list[CharacterSpellResponse]:
        """List all spells known by the character."""

        self.get_character_for_user(character_id, current_user)

        known_spells = self.character_spell_repository.get_known_spells(character_id)
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
        first to make room. The latter two checks are delegated to
        ``CharacterSpellEligibilityChecker``.
        """

        character = self.get_character_for_user(character_id, current_user)

        spell = self.spell_repository.get_by_id(data.spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=data.spell_id)

        existing = self.character_spell_repository.get_known_spell(character_id, data.spell_id)
        if existing:
            raise CharacterSpellAlreadyKnownException(character_id=character_id, spell_id=data.spell_id)

        self.eligibility_checker.check(character, spell)

        character_spell = self.character_spell_repository.add_known_spell(character_id, data.spell_id)
        return CharacterSpellResponse.model_validate(character_spell)

    def remove_known_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> bool:
        """Remove a spell from the character's known spells, freeing up its slot."""

        self.get_character_for_user(character_id, current_user)

        character_spell = self._get_known_spell_or_404(character_id, spell_id)
        return self.character_spell_repository.remove_known_spell(character_spell)

    def _get_known_spell_or_404(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Fetch a known-spell entry, or raise ``CharacterSpellNotFoundException``."""

        character_spell = self.character_spell_repository.get_known_spell(character_id, spell_id)
        if not character_spell:
            raise CharacterSpellNotFoundException(character_id=character_id, spell_id=spell_id)

        return character_spell
