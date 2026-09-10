"""Character item service: the read-only inventory listing (writes are GM-only, served by the GM panel)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.items.repository import CharacterItemRepository
from app.features.characters.items.schemas import CharacterItemResponse
from app.features.users.schemas import UserResponse


class CharacterItemService(CharacterSubDomainService):
    """
    Read-only inventory listing for a character: every independent item
    stack it owns. Writes (add/update/remove) are GM-only and live in
    ``app.features.characters.gm_panel.items``.
    """

    def __init__(self, db: AsyncSession):
        """Create the item-stack repository alongside the shared character access check."""

        super().__init__(db)
        self.character_item_repository = CharacterItemRepository(db)

    async def get_items(self, character_id: int, current_user: UserResponse) -> list[CharacterItemResponse]:
        """List every item stack a character owns (GM/owner readable)."""

        await self.get_character_for_user(character_id, current_user)

        stacks = await self.character_item_repository.get_character_items(character_id)
        return [CharacterItemResponse.model_validate(stack) for stack in stacks]
