"""Character item service: the inventory listing and the sheet's equip toggle (other writes: the GM panel)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.items.repository import CharacterItemRepository
from app.features.characters.items.schemas import CharacterItemEquip, CharacterItemResponse
from app.features.characters.locking import lock_character
from app.features.users.schemas import UserResponse


class CharacterItemService(CharacterSubDomainService):
    """
    Inventory listing for a character: every independent item stack it
    owns, plus the equip toggle anyone with sheet access may use. The other
    writes (add/remove, quantity, attunement) are GM-only and live in
    ``app.features.characters.gm_panel.items``.
    """

    def __init__(self, db: AsyncSession):
        """Create the item-stack repository alongside the shared character access check."""

        super().__init__(db)
        self.character_item_repository = CharacterItemRepository(db)

    async def get_items(self, character_id: int, current_user: UserResponse) -> list[CharacterItemResponse]:
        """List every item stack a character owns (GM/owner readable)."""

        await self.ensure_character_access(character_id, current_user)

        stacks = await self.character_item_repository.get_character_items(character_id)
        return [CharacterItemResponse.model_validate(stack) for stack in stacks]

    async def set_equipped(
        self, character_id: int, stack_id: int, data: CharacterItemEquip, current_user: UserResponse
    ) -> CharacterItemResponse:
        """Equip or unequip one of the character's stacks (owner / campaign GM / founder)."""

        await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            stack = await self.character_item_repository.get_character_item_by_id(character_id, stack_id)
            if stack is None:
                raise RecordNotFoundError(model_name="CharacterItem", model_id=str(stack_id))
            # no cache purge: the cached character response doesn't embed items (combat stats are uncached)
            stack = await self.character_item_repository.update_character_item(stack, {"is_equipped": data.is_equipped})

        return CharacterItemResponse.model_validate(stack)
