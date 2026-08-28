"""Unit tests for GmPanelFeatureService: record/update/remove feature grants."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import FeatureSourceType
from app.features.characters.gm_panel import (
    CharacterFeatureAlreadyKnownException,
    CharacterFeatureNotFoundException,
)
from app.features.characters.gm_panel import CharacterFeatureAdd, CharacterFeatureUpdate
from app.features.characters.gm_panel import GmPanelFeatureService
from app.features.features.exceptions import FeatureNotFoundException
from tests.unit.fakes import FakeAsyncSession, FakeRepository

TOTALS = {
    "strength_total": 14,
    "dexterity_total": 10,
    "constitution_total": 12,
    "intelligence_total": 8,
    "wisdom_total": 9,
    "charisma_total": 11,
}


class FakeStatsService:
    """Records ability-score cache refreshes (feature grants can carry fixed effects)."""

    def __init__(self):
        self.refresh_calls = []

    async def refresh(self, character):
        self.refresh_calls.append(character)


class FakeCharacterFeatureRepository:
    """Serves configured grants; records writes."""

    def __init__(self, db, grants_by_id=None):
        self.db = db
        self._by_id = grants_by_id or {}
        self.add_calls = []
        self.notes_calls = []
        self.remove_calls = []

    async def get_character_feature_by_feature_id(self, character_id, feature_id):
        return next((g for g in self._by_id.values() if g.feature_id == feature_id), None)

    async def get_character_feature_by_id(self, character_id, character_feature_id):
        return self._by_id.get(character_feature_id)

    async def add_character_feature(self, character_id, feature_id, notes):
        grant = SimpleNamespace(
            id=9,
            character_id=character_id,
            feature_id=feature_id,
            notes=notes,
            feature=make_feature_brief(feature_id),
        )
        self.add_calls.append(grant)
        await self.db.commit()
        return grant

    async def update_notes(self, grant, notes):
        grant.notes = notes
        self.notes_calls.append((grant, notes))
        return grant

    async def remove_character_feature(self, grant):
        self.remove_calls.append(grant)
        return True


def make_feature_brief(feature_id: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        id=feature_id,
        name="Rage",
        source_type=FeatureSourceType.CLASS,
        level=None,
        description="",
    )


def make_grant(grant_id=6, feature_id=4) -> SimpleNamespace:
    return SimpleNamespace(
        id=grant_id,
        character_id=1,
        feature_id=feature_id,
        notes="old",
        feature=make_feature_brief(feature_id),
    )


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.gm_panel.features.service.invalidate_character_cache", AsyncMock())


def make_service(character=None, *, grants_by_id=None, feature_exists=True):
    db = FakeAsyncSession()
    service = GmPanelFeatureService(db)
    service.get_character_for_user = AsyncMock(return_value=character or SimpleNamespace(id=1))
    service.feature_repository = FakeRepository(db, existing_by_id={4: SimpleNamespace()} if feature_exists else {})
    service.feature_grant_repository = FakeCharacterFeatureRepository(db, grants_by_id=grants_by_id or {})
    service.stats_service = FakeStatsService()
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddFeature:
    async def test_records_grant_and_refreshes_stats_cache(self):
        character = SimpleNamespace(id=1)
        service = make_service(character, feature_exists=True)

        result = await service.add_feature(1, CharacterFeatureAdd(feature_id=4, notes="homebrew"), SimpleNamespace())

        assert result.id == 9
        assert result.notes == "homebrew"
        assert service.feature_grant_repository.add_calls[0].feature_id == 4
        assert service.stats_service.refresh_calls == [character]
        assert service.repository.db.commits == 1

    async def test_unknown_feature_raises(self):
        service = make_service(feature_exists=False)

        with pytest.raises(FeatureNotFoundException):
            await service.add_feature(1, CharacterFeatureAdd(feature_id=99), SimpleNamespace())

        assert service.feature_grant_repository.add_calls == []

    async def test_duplicate_grant_raises(self):
        existing = make_grant()
        service = make_service(grants_by_id={existing.id: existing})

        with pytest.raises(CharacterFeatureAlreadyKnownException):
            await service.add_feature(1, CharacterFeatureAdd(feature_id=4), SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateFeature:
    async def test_replaces_notes_without_touching_the_score_cache(self):
        grant = make_grant()
        service = make_service(grants_by_id={grant.id: grant})

        result = await service.update_feature(1, grant.id, CharacterFeatureUpdate(notes="new"), SimpleNamespace())

        assert result.notes == "new"
        assert service.feature_grant_repository.notes_calls == [(grant, "new")]
        assert service.stats_service.refresh_calls == []

    async def test_none_notes_collapse_to_empty_string(self):
        grant = make_grant()
        service = make_service(grants_by_id={grant.id: grant})

        await service.update_feature(1, grant.id, CharacterFeatureUpdate(notes=None), SimpleNamespace())

        assert grant.notes == ""

    async def test_missing_grant_raises(self):
        service = make_service()

        with pytest.raises(CharacterFeatureNotFoundException):
            await service.update_feature(1, 42, CharacterFeatureUpdate(notes="x"), SimpleNamespace())


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveFeature:
    async def test_removes_grant_and_refreshes_stats_cache(self):
        character = SimpleNamespace(id=1)
        grant = make_grant()
        service = make_service(character, grants_by_id={grant.id: grant})

        result = await service.remove_feature(1, grant.id, SimpleNamespace())

        assert result is True
        assert service.feature_grant_repository.remove_calls == [grant]
        assert service.stats_service.refresh_calls == [character]

    async def test_missing_grant_raises(self):
        service = make_service()

        with pytest.raises(CharacterFeatureNotFoundException):
            await service.remove_feature(1, 42, SimpleNamespace())
