"""Unit tests for NestedSourceItemService and SourceItemManagerMixin.

``NestedSourceItemService`` is the shared per-source starting-equipment engine
(shared/items/nested_service.py); ``SourceItemManagerMixin`` is exercised
through its host ``ClassItemsService`` (shared/items/mixins.py).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import DiceType, FeatureSourceType
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.features.classes.items.service import ClassItemsService
from app.features.shared.items.nested_service import NestedSourceItemService
from app.features.shared.items.schemas import SourceItemEntry, SourceItemsUpdate
from app.models.class_model import Class
from app.models.source_item_model import SourceItem
from tests.unit.fakes import FakeAsyncSession, FakeRepository


class FakeItemRepository:
    """Stands in for ItemRepository inside NestedSourceItemService."""

    def __init__(self, db, items=None):
        self.db = db
        self.items = items or {}

    async def get_items_by_ids(self, item_ids):
        return [self.items[item_id] for item_id in item_ids if item_id in self.items]


class FakeNestedItems:
    """Stands in for NestedSourceItemService inside ClassItemsService."""

    def __init__(self, db):
        self.db = db
        self.list_calls = []
        self.set_calls = []

    async def list_for_source(self, source_type, source_id):
        self.list_calls.append((source_type, source_id))
        return []

    async def set_items_for_source(self, source_type, source_id, entries, *, commit=True):
        self.set_calls.append((source_type, source_id, entries, commit))


def make_class_row(**overrides) -> SimpleNamespace:
    base = {
        "id": 1,
        "name": "Fighter",
        "hit_dice": DiceType.D10,
        "skill_choice_count": 2,
        "spellcasting_ability": None,
        "description": "",
        "created_by_id": None,
        "primary_abilities": [],
        "saving_throws": [],
        "armor_proficiencies": [],
        "available_skills": [],
        "starting_items": [],
        "spell_slot_progression": [],
        "subclasses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


def make_nested_item_service(items=None):
    db = FakeAsyncSession()
    service = NestedSourceItemService(db)
    service._items = FakeItemRepository(db, items)
    return service, db


def make_class_items_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = ClassItemsService(db)
    service.repository = FakeRepository(db, existing_by_id=existing_by_id, model=Class)
    service._items = FakeNestedItems(db)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestNestedSourceItemService:
    async def test_fk_for_resolves_class_and_background(self):
        service, _ = make_nested_item_service()

        assert service.fk_for(FeatureSourceType.CLASS) == "class_id"
        assert service.fk_for(FeatureSourceType.BACKGROUND) == "background_id"

    async def test_create_items_for_source_is_noop_without_entries(self):
        service, db = make_nested_item_service()

        await service.create_items_for_source(FeatureSourceType.CLASS, 1, None)
        await service.create_items_for_source(FeatureSourceType.CLASS, 1, [])

        assert db.added == []
        assert db.commits == 0
        assert db.flushes == 0

    async def test_create_items_for_source_adds_rows_and_commits(self):
        service, db = make_nested_item_service(items={1: SimpleNamespace(id=1), 2: SimpleNamespace(id=2)})
        entries = [SourceItemEntry(item_id=1, quantity=2), SourceItemEntry(item_id=2, quantity=1)]

        await service.create_items_for_source(FeatureSourceType.CLASS, 3, entries, commit=True)

        assert len(db.added) == 2
        assert all(isinstance(row, SourceItem) for row in db.added)
        assert db.added[0].class_id == 3
        assert db.added[0].item_id == 1
        assert db.added[1].quantity == 1
        assert db.commits == 1

    async def test_create_items_for_source_flushes_when_not_committing(self):
        service, db = make_nested_item_service(items={1: SimpleNamespace(id=1)})

        await service.create_items_for_source(
            FeatureSourceType.BACKGROUND, 4, [SourceItemEntry(item_id=1, quantity=1)], commit=False
        )

        assert db.flushes == 1
        assert db.commits == 0
        assert db.added[0].background_id == 4

    async def test_create_items_for_source_raises_for_missing_item(self):
        service, _ = make_nested_item_service(items={})

        with pytest.raises(RecordIdsInvalidError):
            await service.create_items_for_source(
                FeatureSourceType.CLASS, 3, [SourceItemEntry(item_id=999, quantity=1)]
            )

    async def test_set_items_for_source_deletes_then_adds_and_commits(self):
        service, db = make_nested_item_service(items={1: SimpleNamespace(id=1)})

        await service.set_items_for_source(
            FeatureSourceType.CLASS, 3, [SourceItemEntry(item_id=1, quantity=2)]
        )

        assert db.executes
        assert db.added[0].class_id == 3
        assert db.commits == 1

    async def test_set_items_for_source_flushes_when_not_committing(self):
        service, db = make_nested_item_service(items={1: SimpleNamespace(id=1)})

        await service.set_items_for_source(
            FeatureSourceType.CLASS, 3, [SourceItemEntry(item_id=1, quantity=1)], commit=False
        )

        assert db.flushes == 1
        assert db.commits == 0

    async def test_set_items_for_source_raises_for_missing_item(self):
        service, _ = make_nested_item_service(items={})

        with pytest.raises(RecordIdsInvalidError):
            await service.set_items_for_source(
                FeatureSourceType.CLASS, 3, [SourceItemEntry(item_id=999, quantity=1)]
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestSourceItemManagerMixin:
    async def test_list_items_checks_source_and_lists(self):
        service, _ = make_class_items_service(existing_by_id={1: make_class_row()})

        result = await service.list_items(1)

        assert result == []
        assert service._items.list_calls == [(FeatureSourceType.CLASS, 1)]

    async def test_list_items_raises_when_source_missing(self):
        service, _ = make_class_items_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.list_items(99)

    async def test_set_items_replaces_and_returns_serialized_class(self):
        service, _ = make_class_items_service(existing_by_id={1: make_class_row()})
        data = SourceItemsUpdate(items=[SourceItemEntry(item_id=1, quantity=2)])

        result = await service.set_items(1, data)

        assert result.id == 1
        assert service._items.set_calls == [(FeatureSourceType.CLASS, 1, data.items, True)]
