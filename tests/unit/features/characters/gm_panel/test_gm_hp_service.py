"""Unit tests for GmPanelHpService: the only write path for Character.max_hp."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.characters.gm_panel import MaxHpUpdate
from app.features.characters.gm_panel.hp.service import GmPanelHpService
from app.models.character_model import Character
from tests.unit.fakes import FakeAsyncSession, FakeRepository


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.gm_panel.hp.service.invalidate_character_cache", AsyncMock())


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
        "max_hp": 30,
        "current_hp": 28,
    }
    base.update(overrides)
    return Character(**base)


SENTINEL_RESPONSE = SimpleNamespace(id=1)


def make_service(character):
    db = FakeAsyncSession()
    service = GmPanelHpService(db)
    service.get_character_for_user = AsyncMock(return_value=character)
    service.repository = FakeRepository(db, existing_by_id={character.id: character})
    service._character_response = AsyncMock(return_value=SENTINEL_RESPONSE)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetMaxHp:
    async def test_sets_max_hp_and_serializes_full_response(self):
        character = make_character(current_hp=10)
        service = make_service(character)

        result = await service.set_max_hp(1, MaxHpUpdate(max_hp=35), SimpleNamespace())

        assert result is SENTINEL_RESPONSE
        assert character.max_hp == 35
        assert character.current_hp == 10
        assert len(service.repository.updated) == 1
        service._character_response.assert_awaited_once_with(character)

    async def test_clamps_current_hp_down_to_new_max(self):
        character = make_character(max_hp=40, current_hp=38)
        service = make_service(character)

        await service.set_max_hp(1, MaxHpUpdate(max_hp=20), SimpleNamespace())

        assert service.repository.updated == [character]
        assert character.current_hp == 20
        assert character.max_hp == 20

    async def test_current_hp_equal_to_new_max_is_left_alone(self):
        character = make_character(max_hp=30, current_hp=20)
        service = make_service(character)

        await service.set_max_hp(1, MaxHpUpdate(max_hp=20), SimpleNamespace())

        assert character.current_hp == 20
