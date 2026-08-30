"""
Per-source (nested) starting-equipment service.

The class/background detail responses embed their ``starting_items``
(loaded eagerly alongside the parent records, so ``ClassResponse``/
``BackgroundResponse`` always include them). This service owns the nested
mutation endpoints and the cached listing:

  - reads (``list_for_source``) are cached under the dedicated
    ``nested_items`` namespace, via ``NestedCollectionService`` — the
    ``GET /{source}/{id}/items`` endpoints are served from it;
  - writes (create/set) write ``source_items`` rows keyed by the source's
    polymorphic FK and validate the item IDs against the item catalog.

Invalidation is *not* done inside the mutating methods here: they run
inside the caller's ``_atomic()`` transaction (``commit=False``), and
purging before commit would let a concurrent read repopulate the cache
with pre-commit rows. Instead the caller purges the ``nested_items``
namespace after the transaction commits:

  - the source catalog services include ``"nested_items"`` in their
    ``cache_namespaces`` so their catalog-level create/update/delete
    (``BaseService._invalidate_cache``) purges it too;
  - ``SourceItemManagerMixin.set_items`` invalidates explicitly after its
    own replace write.
"""

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
    """
    Per-source starting-equipment reads and writes behind the
    ``nested_items`` cache namespace.

    The parent catalog services (class/background) each hold one
    instance (``_items``) and expose it through
    :class:`SourceItemManagerMixin` (``list_items`` / ``set_items``) and
    their ``create_*`` methods (nested ``starting_items`` payloads).

    Reads (``list_for_source``) and namespace ``invalidate()`` come from
    ``NestedCollectionService``; ``load_options`` adds the eager
    ``item`` relationship load each row needs (``SourceItemResponse``
    embeds ``ItemBriefResponse``). Only ``fk_for`` and the write methods
    are declared here — unlike features, there's no separate write
    service to delegate to, so writes stay on this class directly.
    """

    model = SourceItem
    response_schema = SourceItemResponse
    cache_namespaces = ("nested_items",)
    load_options = (selectinload(SourceItem.item),)

    def __init__(self, db):
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
        """
        Insert starting-equipment entries for ``source_id`` (used by the
        nested ``starting_items`` create payloads).

        ``commit=False`` leaves the transaction open for the caller.
        """

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
        """
        Fully replace the starting-equipment list for ``source_id``.

        Deletes the source's existing rows, inserts one row per entry,
        then commits (or flushes when ``commit=False``). Item IDs are
        validated against the item catalog first.
        """

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

    # ── Choice groups ──────────────────────────────────────────────

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

        # Validate all item IDs first
        await self._validate_choice_option_item_ids(groups)

        # Delete existing groups (cascade deletes options)
        await self.db.execute(delete(SourceItemChoiceGroup).where(getattr(SourceItemChoiceGroup, fk_name) == source_id))

        # Insert new groups + options
        for idx, group_entry in enumerate(groups):
            group = SourceItemChoiceGroup(
                source_type=source_type,
                pick_count=group_entry.pick_count,
                sort_order=group_entry.sort_order if group_entry.sort_order else idx,
                **{fk_name: source_id},
            )
            self.db.add(group)
            await self.db.flush()  # get group.id

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
