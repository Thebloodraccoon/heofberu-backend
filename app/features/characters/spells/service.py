"""Character spell service: slots and known spells management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.grants.effects import (
    load_character_grant_effects,
    load_spell_responses,
    spell_list,
)
from app.features.characters.locking import lock_character
from app.features.characters.spells.eligibility import CharacterSpellEligibilityChecker
from app.features.characters.spells.exceptions import (
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
)
from app.features.characters.spells.repository import (
    CharacterGrantedSpellRepository,
    CharacterSpellRepository,
    CharacterSpellSlotRepository,
)
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellResponse,
    CharacterSpellsResponse,
    SpellSlotResponse,
)
from app.features.spells.crud.repository import SpellRepository
from app.features.spells.exceptions import SpellNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_spell_model import CharacterSpell


class CharacterSpellService(CharacterSubDomainService):
    """
    Spell slots, known spells, and feature-granted spells for a character.
    There is no "prepared" state and no slot spending: knowing a spell IS
    having it ready, and a level's slot ``total`` (derived from the class/
    level progression) doubles as the cap on known spells of that level;
    feature-granted spells never compete for that budget. Eligibility is
    delegated to ``CharacterSpellEligibilityChecker``.
    """

    def __init__(self, db: AsyncSession):
        """Create the spell collaborators and eligibility checker."""

        super().__init__(db)
        self.character_spell_slot_repository = CharacterSpellSlotRepository(db)
        self.character_spell_repository = CharacterSpellRepository(db)
        self.character_granted_spell_repository = CharacterGrantedSpellRepository(db)
        self.spell_repository = SpellRepository(db)
        self.eligibility_checker = CharacterSpellEligibilityChecker(
            self.character_spell_slot_repository,
            self.character_spell_repository,
        )

    async def get_spells(self, character_id: int, current_user: UserResponse) -> CharacterSpellsResponse:
        """
        Return the whole spellcasting picture: slot totals per level, the
        free-form known spells, the GM's direct grants and the spells the
        character's feature/feat grants give (computed, deduplicated) — each
        a plain list of spells. Slot totals are never client-authored — they
        mirror the class progression.
        """

        await self.get_character_for_user(character_id, current_user)

        slots = await self.character_spell_slot_repository.get_all_spell_slots(character_id)
        known_spells = await self.character_spell_repository.get_known_spells(character_id)
        gm_granted = await self.character_granted_spell_repository.get_granted_spells(character_id)

        grant_effects = await load_character_grant_effects(self.repository.db, character_id)
        feature_spell_ids = {spell_id for _, effects in grant_effects for spell_id in effects.spells}
        feature_spells = spell_list(
            feature_spell_ids, await load_spell_responses(self.repository.db, feature_spell_ids)
        )

        return CharacterSpellsResponse(
            spell_slots=[SpellSlotResponse.model_validate(slot) for slot in slots],
            spells=[CharacterSpellResponse.model_validate(cs.spell) for cs in known_spells],
            gm_spells=[CharacterSpellResponse.model_validate(gs.spell) for gs in gm_granted],
            feature_spells=feature_spells,
        )

    async def add_known_spell(
        self, character_id: int, data: CharacterSpellAdd, current_user: UserResponse
    ) -> CharacterSpellResponse:
        """
        Add a spell to the character's known spells (over the slot-limit
        eligibility checks). Raises ``CharacterSpellAlreadyKnownException``
        on duplicates, ``SpellNotAvailableToCharacterException`` on
        class/race restrictions, ``NoSpellSlotAvailableException`` when the
        level's known-cap is full.
        """

        character = await self.get_character_for_user(character_id, current_user)

        spell = await self.spell_repository.get_by_id(data.spell_id)
        if not spell:
            raise SpellNotFoundException(spell_id=data.spell_id)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)

            if await self.character_spell_repository.get_known_spell(character_id, data.spell_id):
                raise CharacterSpellAlreadyKnownException(character_id=character_id, spell_id=data.spell_id)

            await self.eligibility_checker.check(character, spell)
            await self.character_spell_repository.add_known_spell(character_id, data.spell_id)
            await self._invalidate_character(character_id)

        return CharacterSpellResponse.model_validate(spell)

    async def remove_known_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> None:
        """Remove a spell from the character's known spells, freeing up its slot."""

        await self.get_character_for_user(character_id, current_user)

        character_spell = await self._get_known_spell_or_404(character_id, spell_id)
        async with self._atomic():
            await self.character_spell_repository.remove_known_spell(character_spell)
            await self._invalidate_character(character_id)

    async def _get_known_spell_or_404(self, character_id: int, spell_id: int) -> CharacterSpell:
        """Fetch a known-spell entry, or raise ``CharacterSpellNotFoundException``."""

        character_spell = await self.character_spell_repository.get_known_spell(character_id, spell_id)
        if not character_spell:
            raise CharacterSpellNotFoundException(character_id=character_id, spell_id=spell_id)

        return character_spell
