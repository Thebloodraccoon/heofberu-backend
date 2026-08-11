"""
Per-source (nested) starting-equipment service.

The class/background detail responses embed their ``starting_items``
(loaded eagerly alongside the parent records, so ``ClassResponse``/
``BackgroundResponse`` always include them). This service owns the nested
mutation endpoints and the cached listing:

  - reads (``list_for_source``) are cached under the dedicated
    ``nested_items`` namespace — the ``GET /{source}/{id}/items``
    endpoints are served from it;
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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.core.base_service import BaseService
from app.core.cache import invalidate, use_cache
from app.features.items.repository import ItemRepository, SOURCE_ITEM_FK_BY_SOURCE_TYPE
from app.features.items.schemas import SourceItemEntry, SourceItemResponse
from app.models.source_item_model import SourceItem


class NestedSourceItemService:
    """
    Per-source starting-equipment reads and writes behind the
    ``nested_items`` cache namespace.

    The parent catalog services (class/background) each hold one
    instance (``_items``) and expose it through
    :class:`SourceItemManagerMixin` (``list_items`` / ``set_items``) and
    their ``create_*`` methods (nested ``starting_items`` payloads).
    """

    cache_namespaces = ("nested_items",)

    def __init__(self, db: AsyncSession):
        self.db = db
        self._items = ItemRepository(db)

    @use_cache()
    async def list_for_source(
        self, source_type: FeatureSourceType, source_id: int
    ) -> list[SourceItemResponse]:
        """
        Return every starting-equipment entry owned by ``source_id``
        (ordered by id), each embedding its ``ItemBriefResponse``.

        Cached under the ``nested_items`` namespace; purged by any
        source-level write and by catalog-level create/update/delete.
        """

        fk_name = SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]

        result = await self.db.execute(
            select(SourceItem)
            .options(selectinload(SourceItem.item))
            .where(getattr(SourceItem, fk_name) == source_id)
            .order_by(SourceItem.id)
        )
        return [SourceItemResponse.model_validate(row) for row in result.scalars().unique().all()]

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
        fk_name = SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]

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
        fk_name = SOURCE_ITEM_FK_BY_SOURCE_TYPE[source_type]

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

    async def invalidate(self) -> None:
        """Purge every cached per-source starting-equipment listing."""

        for namespace in self.cache_namespaces:
            await invalidate(namespace)
