"""GM-panel spell service: grant/revoke a free-form (non-feature) spell on a character."""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import unit_of_work
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import (
    CharacterGrantedSpellNotFoundException,
    GrantedSpellAlreadyGrantedException,
)
from app.features.characters.gm_panel.spells.schemas import CharacterGrantedSpellAdd
from app.features.characters.locking import lock_character
from app.features.characters.spells.repository import CharacterGrantedSpellRepository
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.features.spells.exceptions import SpellNotFoundException
from app.features.users.schemas import UserResponse


class GmPanelSpellService(CharacterSubDomainService):
    """
    Manage a character's free-form granted spells (``gm_spells``): any spell
    the GM hands out directly (no class/race eligibility check, no
    feature/feat behind it — like a homebrew boon), at most once per spell.
    Spells from feature/feat grants are computed, not stored, so this
    service can neither see nor remove them.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the granted-spell repository."""

        super().__init__(db)
        self.granted_spell_repository = CharacterGrantedSpellRepository(db)

    async def add_granted_spell(
        self, character_id: int, data: CharacterGrantedSpellAdd, current_user: UserResponse
    ) -> CharacterSpellResponse:
        """Grant any spell to a character directly. **GM only** (enforced by the route)."""

        await self.get_character_for_user(character_id, current_user)

        spell = await self.granted_spell_repository.get_spell(data.spell_id)
        if spell is None:
            raise SpellNotFoundException(spell_id=data.spell_id)

        async with unit_of_work(self.repository.db) as uow:
            await lock_character(self.repository.db, character_id)

            if await self.granted_spell_repository.get_granted_spell(character_id, data.spell_id) is not None:
                raise GrantedSpellAlreadyGrantedException(character_id=character_id, spell_id=data.spell_id)

            await self.granted_spell_repository.add_granted_spell(character_id, data.spell_id)
            await uow.after_commit(partial(invalidate_character_cache, character_id))

        return CharacterSpellResponse.model_validate(spell)

    async def remove_granted_spell(self, character_id: int, spell_id: int, current_user: UserResponse) -> None:
        """
        Revoke a spell the GM granted directly. Only those are stored — a
        spell from a feature/feat grant (``feature_spells``) goes away only
        with its grant.
        """

        await self.get_character_for_user(character_id, current_user)

        row = await self.granted_spell_repository.get_granted_spell(character_id, spell_id)
        if row is None:
            raise CharacterGrantedSpellNotFoundException(character_id=character_id, spell_id=spell_id)

        async with unit_of_work(self.repository.db) as uow:
            await self.granted_spell_repository.remove_granted_spell(row)
            await uow.after_commit(partial(invalidate_character_cache, character_id))
