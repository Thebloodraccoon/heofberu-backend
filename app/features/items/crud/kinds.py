"""
The shared write flow of a kind's items (weapons, armor, tools): create the core + the detail record,
patch the detail record. Each kind's package subclasses :class:`KindItemService` with its detail model and
its own checks — the per-kind rules live with the kind, not in one function for every item.
"""

from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ItemKind
from app.core.base.transaction import TransactionMixin, invalidate_after_commit
from app.core.exceptions import RecordNotFoundError
from app.features.items.cache import ITEM_OWN_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import CORE_FIELDS, ItemResponse
from app.features.items.exceptions import WrongItemKindError
from app.models.items.item_model import Item


class KindItemService(TransactionMixin):
    """
    Create / detail-patch flow of one ``ItemKind``. Subclasses set ``kind``, ``detail_attr`` (the
    ``Item`` relationship and payload field: ``weapon``/``armor``/``tool``) and ``detail_model``, and may
    override :meth:`_check` (422 on details that don't fit together) and :meth:`_after_write` (e.g. a
    weapon's properties).
    """

    kind: ClassVar[ItemKind]
    detail_attr: ClassVar[str]
    detail_model: ClassVar[type[Any]]

    def __init__(self, db: AsyncSession):
        """Use the item repository."""

        self.repository = ItemRepository(db)

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def _check(self, details: dict[str, Any], data: BaseModel, *, item: Item | None, touched: set[str]) -> None:
        """Validate the full detail values (current + changes on a patch: ``item`` set; ``touched`` = fields sent)."""

    async def _after_write(self, item: Item, data: BaseModel) -> None:
        """Extra writes of the kind inside the transaction (flush only)."""

    async def _response(self, item_id: int) -> ItemResponse:
        return ItemResponse.model_validate(await self.repository.get_fresh(item_id))

    async def create(self, data: BaseModel) -> ItemResponse:
        """Create the core (``kind`` from the service) and its detail record in one transaction."""

        details = getattr(data, self.detail_attr).model_dump()
        await self._check(details, data, item=None, touched=set(details))

        async with self._atomic():
            item = await self.repository.create({**data.model_dump(include=set(CORE_FIELDS)), "kind": self.kind})
            await self.repository.add_detail(self.detail_model, item.id, details)
            await self._after_write(item, data)
            # nothing references a brand-new item yet: only the listings change
            await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return await self._response(item.id)

    async def update_details(self, item_id: int, data: BaseModel) -> ItemResponse:
        """PATCH the item's detail record; 409 when the item is of another kind."""

        item = await self.repository.get_by_id(item_id)
        if item is None:
            raise RecordNotFoundError(model_name="Item", model_id=str(item_id))
        if item.kind != self.kind:
            raise WrongItemKindError(item_id, self.kind.value, item.kind.value)

        changes = data.model_dump(exclude_unset=True, exclude={"property_ids"})
        record = getattr(item, self.detail_attr)
        current = {column.key: getattr(record, column.key) for column in self.detail_model.__table__.columns}
        current.pop("item_id")
        await self._check({**current, **changes}, data, item=item, touched=set(data.model_fields_set))

        async with self._atomic():
            await self.repository.update_detail(record, changes)
            await self._after_write(item, data)
            # dependents embed only the item's id/name/kind, none of which a detail PATCH changes
            await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return await self._response(item_id)
