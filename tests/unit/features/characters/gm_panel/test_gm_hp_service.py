"""Unit tests for GmPanelHpService: the only write path for Character.max_hp."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest
from sqlalchemy.dialects import postgresql

from app.features.characters.gm_panel.hp.repository import GmHpRepository
from app.features.characters.gm_panel.hp.schemas import MAX_HP_LIMIT, MaxHpUpdate
from app.features.characters.gm_panel.hp.service import GmPanelHpService
from app.models.character.character_model import Character
from tests.unit.fakes import FakeAsyncSession


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


class FakeHpRepository:
    """Records the atomic max-HP write."""

    def __init__(self):
        self.calls = []

    async def set_max_hp(self, character, max_hp):
        self.calls.append((character, max_hp))


def make_service(character):
    db = FakeAsyncSession()
    service = GmPanelHpService(db)
    service.get_character_for_user = AsyncMock(return_value=character)
    service.hp_repository = FakeHpRepository()
    service._character_response = AsyncMock(return_value=SENTINEL_RESPONSE)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetMaxHp:
    async def test_writes_max_hp_in_one_committed_transaction_and_serializes_the_response(self):
        character = make_character()
        service = make_service(character)

        result = await service.set_max_hp(1, MaxHpUpdate(max_hp=35), SimpleNamespace())

        assert result is SENTINEL_RESPONSE
        assert service.hp_repository.calls == [(character, 35)]
        assert service.repository.db.commits == 1
        service._character_response.assert_awaited_once_with(character)

    async def test_cache_is_invalidated_after_the_commit(self, monkeypatch):
        events = []
        service = make_service(make_character())

        async def commit():
            events.append("commit")

        async def invalidate(character_id):
            events.append("invalidate")

        service.repository.db.commit = commit
        monkeypatch.setattr("app.features.characters.gm_panel.hp.service.invalidate_character_cache", invalidate)

        await service.set_max_hp(1, MaxHpUpdate(max_hp=35), SimpleNamespace())

        assert events == ["commit", "invalidate"]


@pytest.mark.unit
class TestMaxHpUpdateBounds:
    def test_negative_is_rejected(self):
        with pytest.raises(ValidationError):
            MaxHpUpdate(max_hp=-1)

    def test_above_the_limit_is_rejected(self):
        with pytest.raises(ValidationError):
            MaxHpUpdate(max_hp=MAX_HP_LIMIT + 1)

    def test_limit_is_accepted(self):
        assert MaxHpUpdate(max_hp=MAX_HP_LIMIT).max_hp == MAX_HP_LIMIT


class _ReturningDb(FakeAsyncSession):
    """Answers the UPDATE ... RETURNING with the values the database would store."""

    def __init__(self, stored):
        super().__init__()
        self.stored = stored

    async def execute(self, stmt, params=None):
        await super().execute(stmt, params)
        return SimpleNamespace(one=lambda: self.stored)


@pytest.mark.unit
@pytest.mark.asyncio
class TestGmHpRepository:
    async def test_clamps_current_hp_in_the_same_statement(self):
        db = _ReturningDb((20, 20))

        await GmHpRepository(db).set_max_hp(make_character(max_hp=40, current_hp=38), 20)

        sql = str(db.executes[0].compile(dialect=postgresql.dialect())).lower()
        assert "least(characters.current_hp" in sql
        assert "returning" in sql

    async def test_loaded_character_takes_over_the_stored_values(self):
        character = make_character(max_hp=40, current_hp=38)

        await GmHpRepository(_ReturningDb((20, 20))).set_max_hp(character, 20)

        assert (character.max_hp, character.current_hp) == (20, 20)

    async def test_current_hp_below_the_new_max_is_kept(self):
        character = make_character(max_hp=10, current_hp=7)

        await GmHpRepository(_ReturningDb((18, 7))).set_max_hp(character, 18)

        assert (character.max_hp, character.current_hp) == (18, 7)
