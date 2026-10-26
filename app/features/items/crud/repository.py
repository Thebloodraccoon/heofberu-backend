"""Item repository: base CRUD with in-use ownership guard."""

from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType, ItemRarity
from app.core.base.repository import BaseRepository
from app.models.character.character_feature_choice_model import CharacterFeatureChoice
from app.models.character.character_item_model import CharacterItem
from app.models.character.character_proficiency_model import CharacterProficiency
from app.models.features.feature_engine_models import (
    FeatureArmorProficiencyEffect,
    FeatureToolProficiencyEffect,
    FeatureWeaponProficiencyEffect,
)
from app.models.items.item_model import Item, ItemArmorDetails, ItemToolDetails, ItemWeaponDetails
from app.models.items.item_source_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption
from app.models.items.item_source_model import SourceItem
from app.models.items.weapon_property_model import WeaponProperty, item_weapon_properties

SOURCE_ITEM_FK_BY_SOURCE_TYPE: dict[FeatureSourceType, str] = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.BACKGROUND: "background_id",
}


# Listing filters on a kind's detail record: query key -> (detail model, column).
_DETAIL_FILTERS: dict[str, tuple[Any, str]] = {
    "weapon_category": (ItemWeaponDetails, "weapon_category"),
    "armor_category": (ItemArmorDetails, "armor_category"),
    "tool_category": (ItemToolDetails, "tool_category"),
}


_NON_COLUMN_FILTERS = {*_DETAIL_FILTERS, "magic", "property_id"}

# ``ItemGetAllResponse`` columns: the core plus each kind's category, outer-joined from its detail record.
_LISTING_COLUMNS = (
    Item.id,
    Item.name,
    Item.kind,
    Item.subtype,
    Item.rarity,
    Item.cost_gold,
    ItemWeaponDetails.weapon_category,
    ItemArmorDetails.armor_category,
    ItemToolDetails.tool_category,
)


def item_detail_loads(base=None) -> list:
    """
    Eager loads ``ItemResponse`` needs (weapon properties, speed/AC effects — the detail records load with the
    item, ``lazy="joined"``); chained onto ``base`` (a loader for an ``Item``-valued relationship, e.g.
    ``selectinload(CharacterItem.item)``) when given.
    """

    def load(attr):
        return selectinload(attr) if base is None else base.selectinload(attr)

    return [load(Item.properties), load(Item.speed_effects), load(Item.armor_class_effects)]


class ItemRepository(BaseRepository[Item]):
    """Item-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise the item repository with name uniqueness and in-use guard."""

        super().__init__(
            Item,
            db,
            default_load_options=item_detail_loads(),
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    def _apply_filters(self, stmt: Any, filters: dict[str, Any] | None) -> Any:
        """
        The base exact-match filters on the core (``kind``, ``subtype``, ``rarity``), plus: the category of a
        kind's detail record (any of), ``property_id`` (weapons having ALL the given properties) and ``magic``
        (``True``: rarity other than NONE, ``False``: mundane).
        """

        filters = filters or {}
        for key, (model, column) in _DETAIL_FILTERS.items():
            if values := filters.get(key):
                # correlated to ``items`` only: ``get_listing`` also has the detail table in its outer FROM
                condition = exists().where(model.item_id == Item.id, getattr(model, column).in_(values)).correlate(Item)
                stmt = stmt.where(condition)
        if (magic := filters.get("magic")) is not None:
            stmt = stmt.where(Item.rarity != ItemRarity.NONE if magic else Item.rarity == ItemRarity.NONE)

        property_ids = filters.get("property_id") or []
        for property_id in property_ids:
            stmt = stmt.where(
                exists().where(
                    item_weapon_properties.c.item_id == Item.id,
                    item_weapon_properties.c.property_id == property_id,
                )
            )

        # the rest are core columns (the detail-category keys are also read-through properties of ``Item``)
        core = {key: value for key, value in filters.items() if key not in _NON_COLUMN_FILTERS}
        return super()._apply_filters(stmt, core)

    async def get_listing(
        self, *, skip: int = 0, limit: int = 100, filters: dict[str, Any] | None = None, search: str | None = None
    ) -> list[Any]:
        """A page of ``_LISTING_COLUMNS`` rows (no ORM objects), ordered by name then id; same filters as ``count``."""

        stmt = (
            select(*_LISTING_COLUMNS)
            .outerjoin(ItemWeaponDetails, ItemWeaponDetails.item_id == Item.id)
            .outerjoin(ItemArmorDetails, ItemArmorDetails.item_id == Item.id)
            .outerjoin(ItemToolDetails, ItemToolDetails.item_id == Item.id)
        )
        stmt = self._apply_search(self._apply_filters(stmt, filters), search)
        stmt = stmt.order_by(*self._ordering(Item.name)).offset(skip).limit(limit)
        return list((await self.db.execute(stmt)).all())

    async def get_fresh(self, item_id: int) -> Item:
        """Re-read an item with its detail loads, overwriting what the session holds (after a write)."""

        statement = (
            select(Item)
            .where(Item.id == item_id)
            .options(*item_detail_loads())
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(statement)).scalar_one()

    async def lock(self, item_id: int) -> None:
        """Lock the item row (``FOR UPDATE``) so concurrent writes of its children serialise behind it."""

        await self.db.execute(select(Item.id).where(Item.id == item_id).with_for_update())

    async def add_detail(self, detail_model: type[Any], item_id: int, details: dict[str, Any]) -> None:
        """Insert the item's per-kind detail record (flush only)."""

        self.db.add(detail_model(item_id=item_id, **details))
        await self.flush()

    async def update_detail(self, record: Any, changes: dict[str, Any]) -> None:
        """Apply PATCH changes onto a detail record (flush only)."""

        for field, value in changes.items():
            setattr(record, field, value)
        await self.flush()

    async def add_effects(self, rows: list[Any]) -> None:
        """Insert item-owned effect rows (flush only)."""

        self.db.add_all(rows)
        await self.flush()

    async def delete_effect(self, row: Any) -> None:
        """Delete one item-owned effect row (flush only)."""

        await self.db.delete(row)
        await self.flush()

    async def get_properties_by_ids(self, property_ids: list[int]) -> list[WeaponProperty]:
        """Fetch the weapon properties matching ``property_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(WeaponProperty, property_ids)

    async def set_properties(self, item: Item, property_ids: list[int]) -> None:
        """Replace the item's weapon properties (flush only)."""

        await self.replace_association(item_weapon_properties, item, "item_id", "property_id", property_ids)

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

        referencing = (
            (CharacterItem, "item_id"),
            (CharacterProficiency, "item_id"),
            (CharacterFeatureChoice, "picked_item_id"),
            (FeatureWeaponProficiencyEffect, "item_id"),
            (FeatureArmorProficiencyEffect, "item_id"),
            (FeatureToolProficiencyEffect, "item_id"),
            (SourceItem, "item_id"),
            (SourceItemChoiceOption, "item_id"),
        )
        for model, column in referencing:
            if await self.exists_referencing(model, column, item_id):
                return True

        return False

    async def delete(self, db_obj: Item) -> bool:
        """
        Delete the item unless something references it.

        ``character_proficiencies.item_id`` cascades, so a reference added
        between the guard and the DELETE would be wiped silently. Locking the
        item row first makes a concurrent insert (which takes a key-share
        lock on it) wait for this transaction.
        """

        await self.db.execute(select(Item.id).where(Item.id == db_obj.id).with_for_update())
        return await super().delete(db_obj)
