"""Repository for the item stacks owned by a character (``character_items``)."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.features.items.crud.repository import item_detail_loads
from app.models.character.character_item_model import CharacterItem
from app.models.items.item_model import Item


class CharacterItemRepository(BaseRepository[CharacterItem]):
    """
    Repository for the items owned by a character (``character_items``).
    Each row is its own stack — the model allows a character to own several
    stacks of the same item, though ``GmPanelItemService.add_item`` now
    merges a new add into an existing stack rather than creating another.
    Every read eager-loads the referenced ``Item``.
    """

    def __init__(self, db: AsyncSession):
        """Create the item-stack repository."""

        super().__init__(CharacterItem, db)

    @staticmethod
    def _stack_with_item(statement):
        """Return the query with the ``Item`` (and what ``ItemResponse`` embeds) eager-loaded."""

        item_load = selectinload(CharacterItem.item)
        return statement.options(item_load, *item_detail_loads(item_load))

    async def count_attuned(self, character_id: int, *, exclude_stack_id: int | None = None) -> int:
        """
        How many of the character's stacks are attuned (bar ``exclude_stack_id``) — only those whose item still
        requires attunement count (a stale ``is_attuned`` on an item the GM made non-attunable doesn't).
        """

        statement = (
            select(func.count())
            .select_from(CharacterItem)
            .join(Item, Item.id == CharacterItem.item_id)
            .where(CharacterItem.character_id == character_id, CharacterItem.is_attuned, Item.requires_attunement)
        )
        if exclude_stack_id is not None:
            statement = statement.where(CharacterItem.id != exclude_stack_id)
        return await self.db.scalar(statement) or 0

    @staticmethod
    def _equipped_loads() -> list:
        item_load = selectinload(CharacterItem.item)
        return [item_load, item_load.selectinload(Item.speed_effects), item_load.selectinload(Item.armor_class_effects)]

    async def get_equipped_stacks(self, character_id: int) -> list[CharacterItem]:
        """The character's equipped stacks with their item and its speed/AC effects loaded."""

        result = await self.db.execute(
            select(CharacterItem)
            .where(CharacterItem.character_id == character_id, CharacterItem.is_equipped)
            .options(*self._equipped_loads())
            .order_by(CharacterItem.id)
        )
        return list(result.scalars().unique().all())

    async def get_character_items(self, character_id: int) -> list[CharacterItem]:
        """Get every item stack owned by a character."""

        result = await self.db.execute(
            self._stack_with_item(select(CharacterItem).where(CharacterItem.character_id == character_id))
        )
        return list(result.scalars().unique().all())

    async def get_character_item_by_id(self, character_id: int, character_item_id: int) -> CharacterItem | None:
        """Fetch a single item stack by its own id, scoped to the character."""

        result = await self.db.execute(
            self._stack_with_item(
                select(CharacterItem).where(
                    CharacterItem.id == character_item_id,
                    CharacterItem.character_id == character_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_character_item_by_item_id(self, character_id: int, item_id: int) -> CharacterItem | None:
        """
        Fetch the character's existing stack of a given catalog item, if any.

        A character may still end up with more than one stack of the same
        item (this returns the earliest by id); ``add_character_item`` uses
        this to merge a new add into that stack instead of creating another.
        """

        result = await self.db.execute(
            self._stack_with_item(
                select(CharacterItem)
                .where(CharacterItem.character_id == character_id, CharacterItem.item_id == item_id)
                .order_by(CharacterItem.id)
            )
        )
        return result.scalars().first()

    async def get_stacks_by_item_ids(self, character_id: int, item_ids: Iterable[int]) -> list[CharacterItem]:
        """The character's stacks of the given catalog items (``Item`` not loaded)."""

        result = await self.db.execute(
            select(CharacterItem).where(
                CharacterItem.character_id == character_id,
                CharacterItem.item_id.in_(list(item_ids)),
            )
        )
        return list(result.scalars().all())

    async def add_character_item(
        self,
        character_id: int,
        item_id: int,
        quantity: int,
    ) -> CharacterItem:
        """Add a new item stack to a character (see ``GmPanelItemService.add_item`` for the merge-into-existing-stack check)."""

        stack = CharacterItem(
            character_id=character_id,
            item_id=item_id,
            quantity=quantity,
        )

        self.db.add(stack)
        await self.flush()

        return await self._fetch_with_item(stack.id)

    async def update_character_item(self, stack: CharacterItem, fields: dict) -> CharacterItem:
        """Apply a PATCH field dict onto an item stack (flush only)."""

        for field, value in fields.items():
            setattr(stack, field, value)

        await self.flush()

        return await self._fetch_with_item(stack.id)

    async def remove_character_item(self, stack: CharacterItem) -> bool:
        """Remove an item stack from a character."""

        await self.db.delete(stack)
        await self.flush()
        return True

    async def _fetch_with_item(self, stack_id: int) -> CharacterItem:
        """Re-fetch one stack with its item eager-loaded (after the flush)."""

        result = await self.db.execute(self._stack_with_item(select(CharacterItem).where(CharacterItem.id == stack_id)))
        return result.scalar_one()
