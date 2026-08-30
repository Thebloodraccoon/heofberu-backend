"""Unit tests for GmPanelItemService: inventory stacks with GM-write/owner-read access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.characters.gm_panel.exceptions import CharacterItemNotFoundException
from app.features.characters.gm_panel.items.schemas import CharacterItemAdd, CharacterItemUpdate
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

    async def add_character_item(self, character_id, item_id, quantity, is_equipped, is_attuned, notes):
        stack = SimpleNamespace(
            id=self._next_id,
            character_id=character_id,
            item_id=item_id,
            quantity=quantity,
            is_equipped=is_equipped,
            is_attuned=is_attuned,
            notes=notes,
            item=make_item(item_id),
        )
        self._next_id += 1
        self.add_calls.append(stack)
        await self.db.commit()
        await self.db.refresh(stack)
        return stack

    async def update_character_item(self, stack, fields):
        for field, value in fields.items():
            setattr(stack, field, value)
        self.update_calls.append((stack, fields))
        await self.db.commit()
        await self.db.refresh(stack)
        return stack

    async def remove_character_item(self, stack):
        self.remove_calls.append(stack)
        await self.db.commit()
        return True


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.gm_panel.items.service.invalidate_character_cache", AsyncMock())


def make_item(item_id=5) -> SimpleNamespace:
    return SimpleNamespace(id=item_id, name="Longsword", item_type="WEAPON")


def make_stack(stack_id=3, item_id=5, **overrides) -> SimpleNamespace:
    base = {
        "id": stack_id,
        "character_id": 1,
        "item_id": item_id,
        "quantity": 2,
        "is_equipped": False,
        "is_attuned": False,
        "notes": "",
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
            CharacterItemAdd(item_id=5, quantity=4, is_equipped=True, is_attuned=True, notes="loot"),
            SimpleNamespace(),
        )

        assert result.id == 1
        assert result.quantity == 4
        assert service.character_item_repository.add_calls[0].is_equipped is True
        assert service.repository.db.commits == 1

    async def test_unknown_item_raises(self):
        service = make_service(item_exists=False)

        with pytest.raises(ItemNotFoundException):
            await service.add_item(1, CharacterItemAdd(item_id=99), SimpleNamespace())

        assert service.character_item_repository.add_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateItem:
    async def test_applies_patch_fields_only(self):
        stack = make_stack()
        service = make_service(stacks={stack.id: stack})

        data = CharacterItemUpdate(quantity=7, is_equipped=True)
        await service.update_item(1, stack.id, data, SimpleNamespace())

        assert stack.quantity == 7
        assert stack.is_equipped is True
        assert stack.is_attuned is False
        assert service.character_item_repository.update_calls == [(stack, {"quantity": 7, "is_equipped": True})]

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
