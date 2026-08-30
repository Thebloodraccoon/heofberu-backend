"""Character backstory service: get/set a character's backstory (never cached)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.backstory.repository import CharacterBackstoryRepository
from app.features.characters.backstory.schemas import (
    CharacterBackstoryResponse,
    CharacterBackstoryUpdate,
)
from app.features.characters.base import CharacterSubDomainService
from app.features.users.schemas import UserResponse


class CharacterBackstoryService(CharacterSubDomainService):
    """
    Manage a character's backstory (``character_backstories``).

    Unlike the character sheet, the backstory can run several pages of text,
    so it is deliberately served UNcached — no ``@use_cache`` and no
    ``invalidate_character_cache`` on write, because the backstory is never
    part of the cached ``CharacterResponse``. Reads hit the DB directly
    through the owning-character access check.

    ``GET`` returns an empty ``content`` when no row exists (an empty
    backstory is a valid, cheap default); ``PUT`` upserts (creates the row
    on first write). ``READ``/``WRITE`` are available to the GM and owner.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.backstory_repository = CharacterBackstoryRepository(db)

    async def get_backstory(self, character_id: int, current_user: UserResponse) -> CharacterBackstoryResponse:
        """Return the character's backstory (empty string if none recorded). GM/owner readable."""

        await self.get_character_for_user(character_id, current_user)

        row = await self.backstory_repository.get_for_character(character_id)
        if row is None:
            return CharacterBackstoryResponse(character_id=character_id, content="")

        return CharacterBackstoryResponse.model_validate(row)

    async def set_backstory(
        self, character_id: int, data: CharacterBackstoryUpdate, current_user: UserResponse
    ) -> CharacterBackstoryResponse:
        """Replace the character's backstory (upsert). GM/owner writable."""

        await self.get_character_for_user(character_id, current_user)

        row = await self.backstory_repository.upsert_content(character_id, data.content)
        return CharacterBackstoryResponse.model_validate(row)
