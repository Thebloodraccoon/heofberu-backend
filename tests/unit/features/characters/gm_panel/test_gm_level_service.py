"""Unit tests for GmPanelLevelService: the only write path for a character's level cap."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.characters.gm_panel import (
    MaxLevelBelowCharacterLevelException,
    MaxLevelCanOnlyIncreaseException,
)
from app.features.characters.gm_panel import MaxLevelUpdate
from app.features.characters.gm_panel.level.service import GmPanelLevelService
from app.models.character_model import Character
from tests.unit.fakes import FakeAsyncSession


def make_character(**overrides) -> Character:
    base = {
        "id": 1,
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "level": 5,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


class FakeMaxLevelRepository:
    """Serves an optional max-level row; records seeding."""

    def __init__(self, db, row=None):
        self.db = db
        self.row = row
        self.create_calls = []

    async def get_by_character_id(self, character_id):
        return self.row

    async def create_for_character(self, character_id, max_level, *, commit=True):
        self.create_calls.append((character_id, max_level))
        self.row = SimpleNamespace(character_id=character_id, max_level=max_level)
        if commit:
            await self.db.commit()
            await self.db.refresh(self.row)
        return self.row


def make_service(character, *, row=None):
    db = FakeAsyncSession()
    service = GmPanelLevelService(db)
    service.get_character_for_user = AsyncMock(return_value=character)
    service.max_level_repository = FakeMaxLevelRepository(db, row=row)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetMaxLevel:
    async def test_raises_the_cap(self):
        character = make_character(level=5)
        service = make_service(character, row=SimpleNamespace(character_id=1, max_level=5))

        result = await service.set_max_level(1, MaxLevelUpdate(max_level=10), SimpleNamespace())

        assert result.character_id == 1
        assert result.current_level == 5
        assert result.max_level == 10
        assert service.repository.db.commits == 1

    async def test_lowering_is_rejected(self):
        service = make_service(make_character(), row=SimpleNamespace(character_id=1, max_level=8))

        with pytest.raises(MaxLevelCanOnlyIncreaseException) as exc_info:
            await service.set_max_level(1, MaxLevelUpdate(max_level=6), SimpleNamespace())

        assert exc_info.value.status_code == 400
        assert service.repository.db.commits == 0

    async def test_equal_value_is_rejected(self):
        service = make_service(make_character(), row=SimpleNamespace(character_id=1, max_level=8))

        with pytest.raises(MaxLevelCanOnlyIncreaseException):
            await service.set_max_level(1, MaxLevelUpdate(max_level=8), SimpleNamespace())

    async def test_below_current_level_is_rejected(self):
        service = make_service(make_character(level=5), row=SimpleNamespace(character_id=1, max_level=5))

        with pytest.raises(MaxLevelBelowCharacterLevelException) as exc_info:
            await service.set_max_level(1, MaxLevelUpdate(max_level=4), SimpleNamespace())

        assert exc_info.value.character_level == 5

    async def test_missing_row_is_backfilled_at_current_level_first(self):
        character = make_character(level=3)
        service = make_service(character, row=None)

        await service.set_max_level(1, MaxLevelUpdate(max_level=7), SimpleNamespace())

        assert service.max_level_repository.create_calls == [(1, 3)]
        assert service.max_level_repository.row.max_level == 7

    async def test_backfilled_row_blocks_values_at_or_below_current_level(self):
        service = make_service(make_character(level=3), row=None)

        with pytest.raises(MaxLevelCanOnlyIncreaseException):
            await service.set_max_level(1, MaxLevelUpdate(max_level=3), SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetMaxLevel:
    async def test_returns_stored_max_level(self):
        service = make_service(make_character(level=5), row=SimpleNamespace(character_id=1, max_level=12))

        result = await service.get_max_level(1, SimpleNamespace())

        assert result.current_level == 5
        assert result.max_level == 12

    async def test_missing_row_falls_back_to_current_level(self):
        service = make_service(make_character(level=5), row=None)

        result = await service.get_max_level(1, SimpleNamespace())

        assert result.max_level == 5
