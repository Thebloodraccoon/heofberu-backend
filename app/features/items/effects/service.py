"""Item effects service: the speed/AC effects an item gives while a character has it equipped."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import TransactionMixin, invalidate_after_commit
from app.core.exceptions import RecordNotFoundError
from app.features.features.effects.schemas import DUPLICATE_KEY_BY_EFFECT_FIELD, ItemEffectsUpdate
from app.features.items.cache import ITEM_OWN_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.effects.schemas import ItemEffectsResponse
from app.features.items.exceptions import InvalidItemDataError
from app.models.features.feature_engine_models import ITEM_EFFECT_TYPES, FeatureArmorClassEffect, FeatureSpeedEffect
from app.models.items.item_model import Item

_MODEL_BY_EFFECT_TYPE = {"speed": FeatureSpeedEffect, "armor_class": FeatureArmorClassEffect}


class ItemEffectsService(TransactionMixin):
    """
    Read / add / remove an item's effects (``item_id``-owned rows of the speed and AC effect tables). A write
    purges only the ``items`` namespace (items embed their effects; dependents embed just the item's id/name/kind);
    the character AC/speed read is computed on every request, so no character cache is involved.
    """

    def __init__(self, db: AsyncSession):
        """Use the item repository (its detail loads include the effects)."""

        self.repository = ItemRepository(db)

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def _item_or_404(self, item_id: int, *, fresh: bool = False) -> Item:
        item = await (self.repository.get_fresh(item_id) if fresh else self.repository.get_by_id(item_id))
        if item is None:
            raise RecordNotFoundError(model_name="Item", model_id=str(item_id))
        return item

    @staticmethod
    def _response(item: Item) -> ItemEffectsResponse:
        # plain dicts, validated into the effect-group union by pydantic
        return ItemEffectsResponse(item_id=item.id, effects=item.effects)  # type: ignore[arg-type]

    async def get_effects(self, item_id: int) -> ItemEffectsResponse:
        """The item's effect groups."""

        return self._response(await self._item_or_404(item_id))

    async def add_effects(self, item_id: int, data: ItemEffectsUpdate) -> ItemEffectsResponse:
        """
        Insert the payload's items as new effect rows of the item (422 on an id or a duplicate). The item row is
        locked before the duplicate check so two concurrent adds of an equal effect can't both pass it.
        """

        await self._item_or_404(item_id)
        async with self._atomic():
            await self.repository.lock(item_id)
            item = await self._item_or_404(item_id, fresh=True)
            rows = []
            for effect_type, attr in ITEM_EFFECT_TYPES:
                key = DUPLICATE_KEY_BY_EFFECT_FIELD[attr]
                taken = {key(row) for row in getattr(item, attr)}
                for effect in getattr(data, attr) or []:
                    if effect.id is not None:
                        raise InvalidItemDataError("New effects must not carry an id.")
                    if key(effect) in taken:
                        raise InvalidItemDataError(f"An equal {attr} entry already exists.")
                    model = _MODEL_BY_EFFECT_TYPE[effect_type]
                    rows.append(model(item_id=item.id, **effect.model_dump(exclude={"id"})))

            if rows:
                await self.repository.add_effects(rows)
                await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return self._response(await self._item_or_404(item_id, fresh=True))

    async def remove_effect(self, item_id: int, effect_type: str, effect_id: int) -> ItemEffectsResponse:
        """Delete one of the item's effect rows (404 when it isn't this item's), under the item row lock."""

        await self._item_or_404(item_id)
        model = _MODEL_BY_EFFECT_TYPE[effect_type]
        async with self._atomic():
            await self.repository.lock(item_id)
            item = await self._item_or_404(item_id, fresh=True)
            row = next((row for row in getattr(item, f"{effect_type}_effects") if row.id == effect_id), None)
            if row is None:
                raise RecordNotFoundError(model_name=model.__name__, model_id=str(effect_id))
            await self.repository.delete_effect(row)
            await invalidate_after_commit(self.repository.db, *ITEM_OWN_CACHE_NAMESPACES)

        return self._response(await self._item_or_404(item_id, fresh=True))
