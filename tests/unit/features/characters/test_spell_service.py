"""Unit tests for CharacterSpellService write paths: one transaction owner, cap check under the character lock."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.features.characters.cache import character_cache_key
from app.features.characters.spells.exceptions import (
    CharacterSpellAlreadyKnownException,
    CharacterSpellNotFoundException,
    NoSpellSlotAvailableException,
)
from app.features.characters.spells.schemas import CharacterSpellAdd
from app.features.characters.spells.service import CharacterSpellService
from app.features.spells.exceptions import SpellNotFoundException
from tests.unit.fakes import FakeAsyncSession


def make_spell(spell_id=5):
    return SimpleNamespace(
        id=spell_id,
        name="Magic Missile",
        school="EVOCATION",
        level="LEVEL_1",
        cast_time="ACTION",
        range_type="RANGED",
        range_value=120,
        components=[],
        is_material_consumed=False,
        material=None,
        is_ritual=False,
        duration="INSTANTANEOUS",
        is_concentration=False,
        attack_type=None,
        save_stat=None,
        damage_type=None,
        damage_dice_count=None,
        damage_dice_type=None,
        healing_target=None,
        healing_dice_count=None,
        healing_dice_type=None,
        description="Darts of force.",
        higher_levels=None,
    )


class FakeKnownRepository:
    def __init__(self, known=None):
        self.known = known
        self.added = []
        self.removed = []

    async def get_known_spell(self, character_id, spell_id):
        return self.known

    async def add_known_spell(self, character_id, spell_id):
        self.added.append((character_id, spell_id))

    async def remove_known_spell(self, character_spell):
        self.removed.append(character_spell)


def make_service(*, spell=None, known=None, eligibility=None):
    db = FakeAsyncSession()
    service = CharacterSpellService(db)
    service.get_character_for_user = AsyncMock(return_value=SimpleNamespace(id=1))
    service.spell_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=spell))
    service.character_spell_repository = FakeKnownRepository(known=known)
    service.eligibility_checker = SimpleNamespace(check=eligibility or AsyncMock())
    return service, db


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    invalidate = AsyncMock()
    lock = AsyncMock()
    monkeypatch.setattr("app.features.characters.cache.cache_delete_key", invalidate)
    monkeypatch.setattr("app.features.characters.spells.service.lock_character", lock)
    return SimpleNamespace(invalidate=invalidate, lock=lock)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddKnownSpell:
    async def test_adds_commits_once_and_answers_from_the_loaded_spell(self, stubs):
        service, db = make_service(spell=make_spell())

        result = await service.add_known_spell(1, CharacterSpellAdd(spell_id=5), SimpleNamespace())

        assert result.id == 5
        assert service.character_spell_repository.added == [(1, 5)]
        assert db.commits == 1
        assert db.executes == []
        stubs.lock.assert_awaited_once()
        stubs.invalidate.assert_awaited_once_with(character_cache_key(1))

    async def test_unknown_spell_is_404_before_any_lock(self, stubs):
        service, db = make_service(spell=None)

        with pytest.raises(SpellNotFoundException):
            await service.add_known_spell(1, CharacterSpellAdd(spell_id=5), SimpleNamespace())

        stubs.lock.assert_not_awaited()
        assert db.commits == 0

    async def test_duplicate_is_checked_under_the_lock(self, stubs):
        service, db = make_service(spell=make_spell(), known=SimpleNamespace())

        with pytest.raises(CharacterSpellAlreadyKnownException):
            await service.add_known_spell(1, CharacterSpellAdd(spell_id=5), SimpleNamespace())

        stubs.lock.assert_awaited_once()
        assert db.rollbacks == 1
        stubs.invalidate.assert_not_awaited()

    async def test_full_level_rolls_back_without_writing_or_invalidating(self, stubs):
        service, db = make_service(
            spell=make_spell(), eligibility=AsyncMock(side_effect=NoSpellSlotAvailableException(1, "LEVEL_1"))
        )

        with pytest.raises(NoSpellSlotAvailableException):
            await service.add_known_spell(1, CharacterSpellAdd(spell_id=5), SimpleNamespace())

        assert service.character_spell_repository.added == []
        assert db.commits == 0
        stubs.invalidate.assert_not_awaited()

    async def test_spell_id_must_be_positive(self):
        with pytest.raises(ValidationError):
            CharacterSpellAdd(spell_id=0)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveKnownSpell:
    async def test_removes_in_one_transaction(self, stubs):
        known = SimpleNamespace()
        service, db = make_service(known=known)

        await service.remove_known_spell(1, 5, SimpleNamespace())

        assert service.character_spell_repository.removed == [known]
        assert db.commits == 1
        stubs.invalidate.assert_awaited_once_with(character_cache_key(1))

    async def test_unknown_entry_is_404(self):
        service, db = make_service(known=None)

        with pytest.raises(CharacterSpellNotFoundException):
            await service.remove_known_spell(1, 5, SimpleNamespace())

        assert db.commits == 0
