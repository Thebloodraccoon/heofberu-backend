"""GM-panel spell service: grant/revoke a free-form (non-feature) spell on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import (
    CharacterGrantedSpellNotFoundException,
    GrantedSpellNotRemovableException,
)
from app.features.characters.gm_panel.spells.schemas import CharacterGrantedSpellAdd
from app.features.characters.grants.schemas import CharacterGrantedSpellResponse
from app.features.characters.spells.repository import CharacterGrantedSpellRepository
from app.features.spells.crud.repository import SpellRepository
from app.features.spells.exceptions import SpellNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_spell_model import CharacterGrantedSpell


class GmPanelSpellService(CharacterSubDomainService):
    """
    Manage a character's free-form granted spells: any spell the GM hands
    out directly (no class/race eligibility check, no feature/feat behind
    it — like a homebrew boon), same shape as a feature-granted spell.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the granted-spell and spell repositories."""

        super().__init__(db)
        self.granted_spell_repository = CharacterGrantedSpellRepository(db)
        self.spell_repository = SpellRepository(db)

    async def add_granted_spell(
        self, character_id: int, data: CharacterGrantedSpellAdd, current_user: UserResponse
    ) -> CharacterGrantedSpellResponse:
        """Grant any spell to a character directly. **GM only** (enforced by the route)."""

        await self.get_character_for_user(character_id, current_user)

        if not await self.spell_repository.exists_by_id(data.spell_id):
            raise SpellNotFoundException(spell_id=data.spell_id)

        row = await self.granted_spell_repository.add_granted_spell(
            character_id,
            data.spell_id,
            always_prepared=data.always_prepared,
            counts_against_known_limit=data.counts_against_known_limit,
        )
        await invalidate_character_cache(character_id)

        return CharacterGrantedSpellResponse.model_validate(row)

    async def remove_granted_spell(
        self, character_id: int, granted_spell_id: int, current_user: UserResponse
    ) -> bool:
        """
        Revoke a granted spell. Only removes free-form (GM-granted) rows —
        one that came from a feature/feat grant is revoked by removing
        that grant instead, so the effect engine stays the single source
        of truth for anything it materialized.
        """

        await self.get_character_for_user(character_id, current_user)

        row = await self._get_granted_spell_or_404(character_id, granted_spell_id)
        if row.source_character_feature_id is not None:
            raise GrantedSpellNotRemovableException(character_id=character_id, granted_spell_id=granted_spell_id)

        result = await self.granted_spell_repository.remove_granted_spell(row)
        await invalidate_character_cache(character_id)

        return result

    async def _get_granted_spell_or_404(self, character_id: int, granted_spell_id: int) -> CharacterGrantedSpell:
        """Fetch a granted-spell row scoped to the character, or raise ``CharacterGrantedSpellNotFoundException``."""

        row = await self.granted_spell_repository.get_granted_spell_by_id(character_id, granted_spell_id)
        if row is None:
            raise CharacterGrantedSpellNotFoundException(character_id=character_id, granted_spell_id=granted_spell_id)

        return row
