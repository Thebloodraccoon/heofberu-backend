"""GM-panel item service: managing a character's inventory."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.gm_panel.exceptions import (
    CharacterItemNotFoundException,
    CharacterItemQuantityLimitException,
)
from app.features.characters.gm_panel.items.schemas import MAX_ITEM_QUANTITY, CharacterItemAdd, CharacterItemUpdate
from app.features.characters.items.repository import CharacterItemRepository
from app.features.characters.items.schemas import CharacterItemResponse
from app.features.characters.locking import lock_character
from app.features.items.crud.repository import ItemRepository
from app.features.items.exceptions import ItemNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_item_model import CharacterItem


class GmPanelItemService(CharacterSubDomainService):
    """
    Manage the items a character owns (``character_items``), one stack row
    per distinct item. All writes are GM-only; the inventory listing is
    served by character CRUD.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the item-stack and item repositories."""

        super().__init__(db)
        self.character_item_repository = CharacterItemRepository(db)
        self.item_repository = ItemRepository(db)

    async def add_item(
        self, character_id: int, data: CharacterItemAdd, current_user: UserResponse
    ) -> CharacterItemResponse:
        """
        Add an item to a character's inventory. GM-only.

        If the character already has a stack of this item, the added
        quantity is merged into that stack (the earliest one, if somehow more
        than one exists) instead of creating a duplicate stack row; otherwise
        a new stack is created.
        """

        await self.get_character_for_user(character_id, current_user)

        if not await self.item_repository.exists_by_id(data.item_id):
            raise ItemNotFoundException(item_id=data.item_id)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            existing_stack = await self.character_item_repository.get_character_item_by_item_id(
                character_id, data.item_id
            )
            if existing_stack is not None and existing_stack.quantity + data.quantity > MAX_ITEM_QUANTITY:
                raise CharacterItemQuantityLimitException(
                    character_id=character_id, item_id=data.item_id, limit=MAX_ITEM_QUANTITY
                )

            if existing_stack is not None:
                stack = await self.character_item_repository.update_character_item(
                    existing_stack, {"quantity": existing_stack.quantity + data.quantity}
                )
            else:
                stack = await self.character_item_repository.add_character_item(
                    character_id,
                    item_id=data.item_id,
                    quantity=data.quantity,
                )

            await self._invalidate_character(character_id)

        return CharacterItemResponse.model_validate(stack)

    async def update_item(
        self, character_id: int, character_item_id: int, data: CharacterItemUpdate, current_user: UserResponse
    ) -> CharacterItemResponse:
        """Change a stack's quantity. GM-only. PATCH semantics."""

        await self.get_character_for_user(character_id, current_user)

        fields = data.model_dump(exclude_unset=True)
        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            stack = await self._get_stack_or_404(character_id, character_item_id)
            updated_stack = await self.character_item_repository.update_character_item(stack, fields)
            await self._invalidate_character(character_id)

        return CharacterItemResponse.model_validate(updated_stack)

    async def remove_item(self, character_id: int, character_item_id: int, current_user: UserResponse) -> bool:
        """Remove one item stack from a character's inventory. GM-only."""

        await self.get_character_for_user(character_id, current_user)

        async with self._atomic():
            await lock_character(self.repository.db, character_id)
            stack = await self._get_stack_or_404(character_id, character_item_id)
            result = await self.character_item_repository.remove_character_item(stack)
            await self._invalidate_character(character_id)

        return result

    async def _get_stack_or_404(self, character_id: int, character_item_id: int) -> CharacterItem:
        """Fetch an item stack scoped to the character, or raise ``CharacterItemNotFoundException``."""

        stack = await self.character_item_repository.get_character_item_by_id(character_id, character_item_id)
        if not stack:
            raise CharacterItemNotFoundException(character_id=character_id, character_item_id=character_item_id)

        return stack
