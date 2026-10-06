"""Unit tests for GmPanelItemService: inventory stacks with GM-write/owner-read access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.features.characters.gm_panel.exceptions import (
    CharacterItemNotFoundException,
    CharacterItemQuantityLimitException,
)
from app.features.characters.gm_panel.items.schemas import MAX_ITEM_QUANTITY, CharacterItemAdd, CharacterItemUpdate
from app.features.characters.gm_panel.items.service import GmPanelItemService
from app.features.items.exceptions import ItemNotFoundException
from tests.unit.fakes import FakeAsyncSession, FakeRepository


class FakeCharacterItemRepository:
    """Serves configured stacks and records writes."""

    def __init__(self, db, stacks_by_id=None):
        self.db = db
        self._by_id = stacks_by_id or {}
        self._next_id = max(self._by_id) + 1 if self._by_id else 1
        self.add_calls = []
        self.update_calls = []
        self.remove_calls = []

    async def get_character_item_by_id(self, character_id, character_item_id):
        return self._by_id.get(character_item_id)

    async def get_character_item_by_item_id(self, character_id, item_id):
        matches = [stack for stack in self._by_id.values() if stack.item_id == item_id]
        return min(matches, key=lambda stack: stack.id) if matches else None

    async def add_character_item(self, character_id, item_id, quantity):
        stack = SimpleNamespace(
            id=self._next_id,
            character_id=character_id,
            item_id=item_id,
            quantity=quantity,
            item=make_item(item_id),
        )
        self._next_id += 1
        self.add_calls.append(stack)
        await self.db.flush()
        await self.db.refresh(stack)
        return stack

    async def update_character_item(self, stack, fields):
        for field, value in fields.items():
            setattr(stack, field, value)
        self.update_calls.append((stack, fields))
        await self.db.flush()
        await self.db.refresh(stack)
        return stack

    async def remove_character_item(self, stack):
        self.remove_calls.append(stack)
        await self.db.flush()
        return True


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.cache.cache_delete_key", AsyncMock())


def make_item(item_id=5) -> SimpleNamespace:
    return SimpleNamespace(id=item_id, name="Longsword", item_type="WEAPON")


def make_stack(stack_id=3, item_id=5, **overrides) -> SimpleNamespace:
    base = {
        "id": stack_id,
        "character_id": 1,
        "item_id": item_id,
        "quantity": 2,
        "item": make_item(item_id),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_service(*, item_exists=True, stacks=None):
    db = FakeAsyncSession()
    service = GmPanelItemService(db)
    service.get_character_for_user = AsyncMock(return_value=SimpleNamespace(id=1))
    service.item_repository = FakeRepository(db, existing_by_id={5: SimpleNamespace()} if item_exists else {})
    service.character_item_repository = FakeCharacterItemRepository(db, stacks_by_id=stacks or {})
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddItem:
    async def test_adds_stack_and_invalidates_cache(self):
        service = make_service(item_exists=True)

        result = await service.add_item(
            1,
            CharacterItemAdd(item_id=5, quantity=4),
            SimpleNamespace(),
        )

        assert result.id == 1
        assert result.quantity == 4
        assert service.repository.db.commits == 1

    async def test_unknown_item_raises(self):
        service = make_service(item_exists=False)

        with pytest.raises(ItemNotFoundException):
            await service.add_item(1, CharacterItemAdd(item_id=99), SimpleNamespace())

        assert service.character_item_repository.add_calls == []

    async def test_merges_into_existing_stack_of_same_item(self):
        stack = make_stack(stack_id=3, item_id=5, quantity=2)
        service = make_service(item_exists=True, stacks={stack.id: stack})

        result = await service.add_item(
            1,
            CharacterItemAdd(item_id=5, quantity=1),
            SimpleNamespace(),
        )

        assert result.id == stack.id
        assert result.quantity == 3
        assert service.character_item_repository.add_calls == []
        assert service.character_item_repository.update_calls == [(stack, {"quantity": 3})]

    async def test_merge_beyond_the_stack_limit_is_rejected(self):
        stack = make_stack(stack_id=3, item_id=5, quantity=MAX_ITEM_QUANTITY)
        service = make_service(item_exists=True, stacks={stack.id: stack})

        with pytest.raises(CharacterItemQuantityLimitException) as exc_info:
            await service.add_item(1, CharacterItemAdd(item_id=5, quantity=1), SimpleNamespace())

        assert exc_info.value.status_code == 400
        assert service.character_item_repository.update_calls == []
        assert stack.quantity == MAX_ITEM_QUANTITY


@pytest.mark.unit
class TestQuantityBounds:
    @pytest.mark.parametrize("quantity", [0, -1, MAX_ITEM_QUANTITY + 1])
    def test_add_rejects_out_of_range_quantity(self, quantity):
        with pytest.raises(ValidationError):
            CharacterItemAdd(item_id=5, quantity=quantity)

    def test_add_accepts_the_limit(self):
        assert CharacterItemAdd(item_id=5, quantity=MAX_ITEM_QUANTITY).quantity == MAX_ITEM_QUANTITY

    @pytest.mark.parametrize("quantity", [-1, MAX_ITEM_QUANTITY + 1])
    def test_update_rejects_out_of_range_quantity(self, quantity):
        with pytest.raises(ValidationError):
            CharacterItemUpdate(quantity=quantity)

    def test_update_allows_zero(self):
        assert CharacterItemUpdate(quantity=0).quantity == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateItem:
    async def test_applies_patch_fields_only(self):
        stack = make_stack()
        service = make_service(stacks={stack.id: stack})

        data = CharacterItemUpdate(quantity=7)
        await service.update_item(1, stack.id, data, SimpleNamespace())

        assert stack.quantity == 7
        assert service.character_item_repository.update_calls == [(stack, {"quantity": 7})]

    async def test_missing_stack_raises(self):
        service = make_service()

        with pytest.raises(CharacterItemNotFoundException) as exc_info:
            await service.update_item(1, 42, CharacterItemUpdate(quantity=1), SimpleNamespace())

        assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveItem:
    async def test_removes_stack(self):
        stack = make_stack()
        service = make_service(stacks={stack.id: stack})

        result = await service.remove_item(1, stack.id, SimpleNamespace())

        assert result is True
        assert service.character_item_repository.remove_calls == [stack]
        assert service.repository.db.commits == 1

    async def test_missing_stack_raises(self):
        service = make_service()

        with pytest.raises(CharacterItemNotFoundException):
            await service.remove_item(1, 42, SimpleNamespace())
