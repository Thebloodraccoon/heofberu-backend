"""Unit tests for GmPanelSpellService: one transaction, duplicate check under the character lock, no re-select."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.features.characters.gm_panel.exceptions import (
    CharacterGrantedSpellNotFoundException,
    GrantedSpellAlreadyGrantedException,
)
from app.features.characters.gm_panel.spells.schemas import CharacterGrantedSpellAdd
from app.features.characters.gm_panel.spells.service import GmPanelSpellService
from app.features.spells.exceptions import SpellNotFoundException
from tests.unit.fakes import FakeAsyncSession
from tests.unit.features.characters.test_spell_service import make_spell


class FakeGrantedRepository:
    def __init__(self, spell=None, existing=None):
        self.spell = spell
        self.existing = existing
        self.added = []
        self.removed = []

    async def get_spell(self, spell_id):
        return self.spell

    async def get_granted_spell(self, character_id, spell_id):
        return self.existing

    async def add_granted_spell(self, character_id, spell_id):
        self.added.append((character_id, spell_id))

    async def remove_granted_spell(self, row):
        self.removed.append(row)


def make_service(**repository_kwargs):
    db = FakeAsyncSession()
    service = GmPanelSpellService(db)
    service.get_character_for_user = AsyncMock(return_value=SimpleNamespace(id=1))
    service.granted_spell_repository = FakeGrantedRepository(**repository_kwargs)
    return service, db


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    invalidate = AsyncMock()
    lock = AsyncMock()
    monkeypatch.setattr("app.features.characters.gm_panel.spells.service.invalidate_character_cache", invalidate)
    monkeypatch.setattr("app.features.characters.gm_panel.spells.service.lock_character", lock)
    return SimpleNamespace(invalidate=invalidate, lock=lock)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddGrantedSpell:
    async def test_grants_commits_once_and_answers_from_the_fetched_spell(self, stubs):
        service, db = make_service(spell=make_spell())

        result = await service.add_granted_spell(1, CharacterGrantedSpellAdd(spell_id=5), SimpleNamespace())

        assert result.id == 5
        assert service.granted_spell_repository.added == [(1, 5)]
        assert db.commits == 1
        stubs.lock.assert_awaited_once()
        stubs.invalidate.assert_awaited_once_with(1)

    async def test_unknown_spell_is_404(self):
        service, db = make_service(spell=None)

        with pytest.raises(SpellNotFoundException):
            await service.add_granted_spell(1, CharacterGrantedSpellAdd(spell_id=5), SimpleNamespace())

        assert db.commits == 0

    async def test_duplicate_grant_is_a_409_and_rolls_back(self, stubs):
        service, db = make_service(spell=make_spell(), existing=SimpleNamespace())

        with pytest.raises(GrantedSpellAlreadyGrantedException) as exc_info:
            await service.add_granted_spell(1, CharacterGrantedSpellAdd(spell_id=5), SimpleNamespace())

        assert exc_info.value.status_code == 409
        assert service.granted_spell_repository.added == []
        assert db.rollbacks == 1
        stubs.invalidate.assert_not_awaited()

    async def test_spell_id_must_be_positive(self):
        with pytest.raises(ValidationError):
            CharacterGrantedSpellAdd(spell_id=0)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveGrantedSpell:
    async def test_revokes_in_one_transaction(self, stubs):
        row = SimpleNamespace()
        service, db = make_service(existing=row)

        await service.remove_granted_spell(1, 5, SimpleNamespace())

        assert service.granted_spell_repository.removed == [row]
        assert db.commits == 1
        stubs.invalidate.assert_awaited_once_with(1)

    async def test_missing_grant_is_404(self):
        service, db = make_service(existing=None)

        with pytest.raises(CharacterGrantedSpellNotFoundException):
            await service.remove_granted_spell(1, 5, SimpleNamespace())

        assert db.commits == 0
