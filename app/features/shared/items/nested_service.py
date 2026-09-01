"""Per-source starting-equipment service with cached reads and polymorphic writes."""

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.core.base.nested_service import NestedCollectionService
from app.core.base.service import BaseService
from app.features.items.crud.repository import SOURCE_ITEM_FK_BY_SOURCE_TYPE, ItemRepository
from app.features.shared.items.schemas import (
    ChoiceGroupEntry,
    ChoiceGroupResponse,
    ChoiceGroupsResponse,
    SourceItemEntry,
    SourceItemResponse,
)
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption
from app.models.source_item_model import SourceItem


class NestedSourceItemService(NestedCollectionService[SourceItem, SourceItemResponse]):
    """Per-source starting-equipment reads and writes behind the nested_items cache."""

    model = SourceItem
    response_schema = SourceItemResponse
    cache_namespaces = ("nested_items",)
    load_options = (selectinload(SourceItem.item),)

    def __init__(self, db):
        """Initialise with an item repository for ID validation."""

        super().__init__(db)
        self._items = ItemRepository(db)

    def fk_for(self, source_type: FeatureSourceType) -> str:
        """Resolve the polymorphic FK column for ``source_type``."""

        return SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]

    async def create_items_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        entries: list[SourceItemEntry] | None,
        *,
        commit: bool = False,
    ) -> None:
        """Insert starting-equipment entries for ``source_id``; caller controls commit."""

        if not entries:
            return

        await self._validate_item_ids(entries)
        fk_name = self.fk_for(source_type)

        for entry in entries:
            self.db.add(
                SourceItem(
                    source_type=source_type,
                    item_id=entry.item_id,
                    quantity=entry.quantity,
                    **{fk_name: source_id},
                )
            )

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def set_items_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        entries: list[SourceItemEntry],
        *,
        commit: bool = True,
    ) -> None:
        """Fully replace starting-equipment for ``source_id``; validates item IDs first."""

        await self._validate_item_ids(entries)
        fk_name = self.fk_for(source_type)

        await self.db.execute(delete(SourceItem).where(getattr(SourceItem, fk_name) == source_id))

        for entry in entries:
            self.db.add(
                SourceItem(
                    source_type=source_type,
                    item_id=entry.item_id,
                    quantity=entry.quantity,
                    **{fk_name: source_id},
                )
            )

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def _validate_item_ids(self, entries: list[SourceItemEntry]) -> None:
        """Raise ``RecordIdsInvalidError`` if any entry references a nonexistent item."""

        item_ids = [entry.item_id for entry in entries]
        if item_ids:
            await BaseService.resolve_ids(self._items.get_items_by_ids, item_ids, "Item")

    async def _validate_choice_option_item_ids(self, groups: list[ChoiceGroupEntry]) -> None:
        """Raise ``RecordIdsInvalidError`` if any option references a nonexistent item."""

        item_ids = [opt.item_id for group in groups for opt in group.options]
        if item_ids:
            await BaseService.resolve_ids(self._items.get_items_by_ids, item_ids, "Item")

    async def list_choice_groups_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
    ) -> ChoiceGroupsResponse:
        """Return every choice group (with nested options) for ``source_id``."""

        fk_name = SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]
        stmt = (
            select(SourceItemChoiceGroup)
            .where(getattr(SourceItemChoiceGroup, fk_name) == source_id)
            .options(
                selectinload(SourceItemChoiceGroup.options).selectinload(SourceItemChoiceOption.item),
            )
            .order_by(SourceItemChoiceGroup.sort_order, SourceItemChoiceGroup.id)
        )
        result = await self.db.execute(stmt)
        groups = list(result.scalars().all())

        return ChoiceGroupsResponse(
            source_type=source_type.value,
            source_id=source_id,
            choice_groups=[ChoiceGroupResponse.model_validate(g) for g in groups],
        )

    async def set_choice_groups_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        groups: list[ChoiceGroupEntry],
        *,
        commit: bool = False,
    ) -> ChoiceGroupsResponse:
        """Fully replace the choice groups for ``source_id``."""

        fk_name = SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]

        await self._validate_choice_option_item_ids(groups)

        await self.db.execute(delete(SourceItemChoiceGroup).where(getattr(SourceItemChoiceGroup, fk_name) == source_id))

        for idx, group_entry in enumerate(groups):
            group = SourceItemChoiceGroup(
                source_type=source_type,
                pick_count=group_entry.pick_count,
                sort_order=group_entry.sort_order if group_entry.sort_order else idx,
                **{fk_name: source_id},
            )
            self.db.add(group)
            await self.db.flush()

            for opt_idx, opt_entry in enumerate(group_entry.options):
                option = SourceItemChoiceOption(
                    group_id=group.id,
                    item_id=opt_entry.item_id,
                    quantity=opt_entry.quantity,
                    sort_order=opt_idx,
                )
                self.db.add(option)

        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

        return await self.list_choice_groups_for_source(source_type, source_id)
