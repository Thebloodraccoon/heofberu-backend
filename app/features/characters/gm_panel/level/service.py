"""GM max-level service: the only write path for a character's level cap."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.gm_panel.exceptions import (
    MaxLevelBelowCharacterLevelException,
    MaxLevelCanOnlyIncreaseException,
)
from app.features.characters.gm_panel.level.schemas import CharacterMaxLevelResponse, MaxLevelUpdate
from app.features.characters.level.repository import CharacterMaxLevelRepository
from app.features.users.schemas import UserResponse


class GmPanelLevelService(CharacterSubDomainService):
    """Raise a character's maximum allowed level (GM-only); the cap can only move up."""

    def __init__(self, db: AsyncSession):
        """Wire up the max-level repository."""

        super().__init__(db)
        self.max_level_repository = CharacterMaxLevelRepository(db)

    async def set_max_level(
        self, character_id: int, data: MaxLevelUpdate, current_user: UserResponse
    ) -> CharacterMaxLevelResponse:
        """
        Raise a character's maximum allowed level; the cap can only move
        up (a missing row is seeded at the current level).
        """

        character = await self.get_character_for_user(character_id, current_user)

        row = await self.max_level_repository.get_by_character_id(character_id)
        if row is None:
            row = await self.max_level_repository.create_for_character(character_id, character.level)

        if data.max_level < character.level:
            raise MaxLevelBelowCharacterLevelException(
                character_id=character_id, max_level=data.max_level, character_level=character.level
            )
        if data.max_level <= row.max_level:
            raise MaxLevelCanOnlyIncreaseException(character_id=character_id, current_max_level=row.max_level)

        row.max_level = data.max_level
        await self.max_level_repository.db.commit()
        await self.max_level_repository.db.refresh(row)

        return CharacterMaxLevelResponse(
            character_id=character_id, current_level=character.level, max_level=row.max_level
        )

    async def get_max_level(self, character_id: int, current_user: UserResponse) -> CharacterMaxLevelResponse:
        """Return the character's current level and its GM-set maximum."""

        character = await self.get_character_for_user(character_id, current_user)

        row = await self.max_level_repository.get_by_character_id(character_id)
        max_level = row.max_level if row is not None else character.level

        return CharacterMaxLevelResponse(character_id=character_id, current_level=character.level, max_level=max_level)
