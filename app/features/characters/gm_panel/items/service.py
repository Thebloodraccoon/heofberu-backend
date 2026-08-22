"""GM-panel item service: managing a character's inventory."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import CharacterItemNotFoundException
from app.features.characters.gm_panel.items.repository import CharacterItemRepository
from app.features.characters.gm_panel.items.schemas import (
    CharacterItemAdd,
    CharacterItemResponse,
    CharacterItemUpdate,
)
from app.features.items.crud.repository import ItemRepository
from app.features.items.exceptions import ItemNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_item_model import CharacterItem


class GmPanelItemService(CharacterSubDomainService):
    """
    Manage the items a character owns (``character_items``) — a GM-panel
    capability.

    Each row is an independent stack of an item, so the same item may be
    owned several times. Reads are GM/owner; every WRITE is GM-only
    (routed through ``GmUserDep``) — inventory changes are a GM-panel
    concern. Uses three collaborators:

      - the inherited ``CharacterSubDomainService`` — access control
        only (fetching the owning character to check GM/owner permission
        via ``get_character_for_user``); no inventory data lives there.
      - ``CharacterItemRepository`` — the ``character_items`` stack rows
        (CRUD).
      - ``ItemRepository`` — looking up the reference item being added,
        so stacks always point at an existing item.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.character_item_repository = CharacterItemRepository(db)
        self.item_repository = ItemRepository(db)

    async def get_items(self, character_id: int, current_user: UserResponse) -> list[CharacterItemResponse]:
        """List every item stack owned by a character."""

        await self.get_character_for_user(character_id, current_user)

        stacks = await self.character_item_repository.get_character_items(character_id)
        return [CharacterItemResponse.model_validate(stack) for stack in stacks]

    async def add_item(
        self, character_id: int, data: CharacterItemAdd, current_user: UserResponse
    ) -> CharacterItemResponse:
        """Add one item stack to a character's inventory. GM-only."""

        await self.get_character_for_user(character_id, current_user)

        if not await self.item_repository.exists_by_id(data.item_id):
            raise ItemNotFoundException(item_id=data.item_id)

        stack = await self.character_item_repository.add_character_item(
            character_id,
            data.item_id,
            data.quantity,
            data.is_equipped,
            data.is_attuned,
            data.notes,
        )
        await invalidate_character_cache(character_id)

        return CharacterItemResponse.model_validate(stack)

    async def update_item(
        self, character_id: int, character_item_id: int, data: CharacterItemUpdate, current_user: UserResponse
    ) -> CharacterItemResponse:
        """Change a stack's quantity/equip/attunement/notes. GM-only. PATCH semantics."""

        await self.get_character_for_user(character_id, current_user)

        stack = await self._get_stack_or_404(character_id, character_item_id)

        fields = data.model_dump(exclude_unset=True)
        updated_stack = await self.character_item_repository.update_character_item(stack, fields)
        await invalidate_character_cache(character_id)

        return CharacterItemResponse.model_validate(updated_stack)

    async def remove_item(self, character_id: int, character_item_id: int, current_user: UserResponse) -> bool:
        """Remove one item stack from a character's inventory. GM-only."""

        await self.get_character_for_user(character_id, current_user)

        stack = await self._get_stack_or_404(character_id, character_item_id)
        result = await self.character_item_repository.remove_character_item(stack)
        await invalidate_character_cache(character_id)

        return result

    async def _get_stack_or_404(self, character_id: int, character_item_id: int) -> CharacterItem:
        """Fetch an item stack scoped to the character, or raise ``CharacterItemNotFoundException``."""

        stack = await self.character_item_repository.get_character_item_by_id(character_id, character_item_id)
        if not stack:
            raise CharacterItemNotFoundException(character_id=character_id, character_item_id=character_item_id)

        return stack
