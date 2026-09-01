"""Item repository: base CRUD with in-use ownership guard."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.core.base.repository import BaseRepository
from app.models.character_item_model import CharacterItem
from app.models.item_model import Item
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption
from app.models.source_item_model import SourceItem

SOURCE_ITEM_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.BACKGROUND: "background_id",
}


class ItemRepository(BaseRepository[Item]):
    """Item-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise the item repository with name uniqueness and in-use guard."""

        super().__init__(
            Item,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def get_items_by_ids(self, item_ids: list[int]) -> list[Item]:
        """Fetch the items matching ``item_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Item, item_ids)

    async def get_source_items_for_sources(self, sources: list[tuple[FeatureSourceType, int]]) -> list[SourceItem]:
        """Return the starting-equipment rows owned by the given ``(source_type, source_id)`` pairs."""

        if not sources:
            return []

        conditions = [
            getattr(SourceItem, SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]) == source_id
            for source_type, source_id in sources
        ]

        result = await self.db.execute(select(SourceItem).where(or_(*conditions)))
        return list(result.scalars().all())

    async def get_choice_groups_for_sources(
        self, sources: list[tuple[FeatureSourceType, int]]
    ) -> list[SourceItemChoiceGroup]:
        """Return the choice groups (with options) owned by the given ``(source_type, source_id)`` pairs."""

        if not sources:
            return []

        conditions = [
            getattr(SourceItemChoiceGroup, SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]) == source_id
            for source_type, source_id in sources
        ]

        result = await self.db.execute(
            select(SourceItemChoiceGroup)
            .where(or_(*conditions))
            .options(selectinload(SourceItemChoiceGroup.options))
            .order_by(SourceItemChoiceGroup.sort_order, SourceItemChoiceGroup.id)
        )
        return list(result.scalars().all())

    async def is_in_use(self, item_id: int) -> bool:
        """Return whether the item is referenced anywhere that blocks deletion."""

        if await self.exists_referencing(CharacterItem, "item_id", item_id):
            return True

        if await self.exists_referencing(SourceItem, "item_id", item_id):
            return True

        return await self.exists_referencing(SourceItemChoiceOption, "item_id", item_id)
