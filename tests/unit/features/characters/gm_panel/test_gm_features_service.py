"""Unit tests for GmPanelFeatureService: record/remove feature grants."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import FeatureSourceType, GrantSource
from app.features.characters.gm_panel.exceptions import (
    CharacterFeatureAlreadyKnownException,
    CharacterFeatureNotFoundException,
    FeatureIsAFeatException,
)
from app.features.characters.gm_panel.features.schemas import CharacterFeatureAdd
from app.features.characters.gm_panel.features.service import GmPanelFeatureService
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
        self.refresh_error = None

    async def refresh(self, character):
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_calls.append(character)


class FakeCharacterFeatureRepository:
    """Serves configured grants; records writes."""

    def __init__(self, db, grants_by_id=None):
        self.db = db
        self._by_id = grants_by_id or {}
        self.add_calls = []
        self.remove_calls = []

    async def get_character_feature_by_feature_id(self, character_id, feature_id):
        return next((g for g in self._by_id.values() if g.feature_id == feature_id), None)

    async def get_character_feature_by_id(self, character_id, character_feature_id):
        return self._by_id.get(character_feature_id)

    async def add_character_feature(self, character_id, feature_id, *, grant_source=GrantSource.GM):
        grant = SimpleNamespace(
            id=9,
            character_id=character_id,
            feature_id=feature_id,
            grant_source=grant_source,
            feature=make_feature_brief(feature_id),
        )
        self.add_calls.append(grant)
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
        grant_source=GrantSource.GM,
        feature=make_feature_brief(feature_id),
    )


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.cache.cache_delete_key", AsyncMock())


def make_service(character=None, *, grants_by_id=None, feature_exists=True):
    db = FakeAsyncSession()
    service = GmPanelFeatureService(db)
    service.get_character_for_user = AsyncMock(return_value=character or SimpleNamespace(id=1))
    service.feature_repository = FakeRepository(
        db, existing_by_id={4: SimpleNamespace(source_type=FeatureSourceType.CLASS)} if feature_exists else {}
    )
    service.feature_grant_repository = FakeCharacterFeatureRepository(db, grants_by_id=grants_by_id or {})
    service.stats_service = FakeStatsService()
    service.grant_service = SimpleNamespace(resolve_grant_choices=AsyncMock(return_value=None))
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddFeature:
    async def test_records_grant_and_refreshes_stats_cache(self):
        character = SimpleNamespace(id=1)
        service = make_service(character, feature_exists=True)

        result = await service.add_feature(1, CharacterFeatureAdd(feature_id=4), SimpleNamespace())

        assert result.id == 9
        assert service.feature_grant_repository.add_calls[0].feature_id == 4
        assert service.feature_grant_repository.add_calls[0].grant_source == GrantSource.GM
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

    async def test_gm_grant_of_feat_source_type_raises(self):
        feat_feature = SimpleNamespace(id=5, source_type=FeatureSourceType.FEAT)
        service = make_service(SimpleNamespace(id=1))
        service.feature_repository = FakeRepository(FakeAsyncSession(), existing_by_id={5: feat_feature})

        with pytest.raises(FeatureIsAFeatException):
            await service.add_feature(1, CharacterFeatureAdd(feature_id=5), SimpleNamespace())

    async def test_gm_grant_resolves_choices_without_enforcing(self):
        """Effects are computed on read — the grant only records picks, and a GM grant may leave groups pending."""
        service = make_service(SimpleNamespace(id=1), feature_exists=True)

        await service.add_feature(1, CharacterFeatureAdd(feature_id=4), SimpleNamespace())

        resolve = service.grant_service.resolve_grant_choices
        assert resolve.call_count == 1
        assert resolve.call_args.kwargs == {"enforce": False}


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
        assert service.repository.db.commits == 1

    async def test_failing_refresh_rolls_the_removal_back(self):
        grant = make_grant()
        service = make_service(SimpleNamespace(id=1), grants_by_id={grant.id: grant})
        service.stats_service.refresh_error = RuntimeError("refresh failed")

        with pytest.raises(RuntimeError):
            await service.remove_feature(1, grant.id, SimpleNamespace())

        assert (service.repository.db.commits, service.repository.db.rollbacks) == (0, 1)

    async def test_missing_grant_raises(self):
        service = make_service()

        with pytest.raises(CharacterFeatureNotFoundException):
            await service.remove_feature(1, 42, SimpleNamespace())
