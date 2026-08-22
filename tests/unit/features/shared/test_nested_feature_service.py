"""
Unit tests for NestedFeatureService and SourceFeatureMixin.

``NestedFeatureService`` is the shared per-source feature read/write engine
(shared/features/nested_service.py); ``SourceFeatureMixin`` is exercised
through its host ``RaceFeatureService`` (shared/features/mixins.py).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import FeatureSourceType
from app.core.exceptions import RecordNotFoundError
from app.features.races.features.service import RaceFeatureService
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate
from app.models.race_model import Race
from tests.unit.fakes import FakeAsyncSession, FakeRepository


class FakeFeatureCrudService:
    """Stands in for FeatureCrudService inside NestedFeatureService."""

    def __init__(self, db):
        self.db = db
        self.calls = []

    async def create_feature_for_source(self, source_type, source_id, item, created_by_id, *, commit=False):
        self.calls.append(("create", source_type, source_id, item, created_by_id, commit))
        return SimpleNamespace(id=1, name=item.name, description=item.description, level=item.level)

    async def create_features_for_source(self, source_type, source_id, items, created_by_id, *, commit=False):
        self.calls.append(("create_many", source_type, source_id, items, created_by_id, commit))
        return [
            SimpleNamespace(id=i, name=item.name, description=item.description, level=item.level)
            for i, item in enumerate((items or []), start=1)
        ]

    async def update_feature_for_source(self, source_type, source_id, feature_id, fields, *, commit=False):
        self.calls.append(("update", source_type, source_id, feature_id, fields, commit))
        return SimpleNamespace(
            id=feature_id,
            name=fields.get("name", "Extra Attack"),
            description=fields.get("description", ""),
            level=fields.get("level"),
        )

    async def delete_feature_for_source(self, source_type, source_id, feature_id, *, commit=False):
        self.calls.append(("delete", source_type, source_id, feature_id, commit))


class FakeNestedFeatures:
    """Stands in for NestedFeatureService inside RaceFeatureService."""

    def __init__(self, db):
        self.db = db
        self.list_calls = []
        self.created = []
        self.updated = []
        self.deleted = []
        self.invalidate_calls = 0

    async def list_for_source(self, source_type, source_id):
        self.list_calls.append((source_type, source_id))
        return []

    async def create_feature_for_source(self, source_type, source_id, item, created_by_id, *, commit=False):
        self.created.append((source_type, source_id, item, created_by_id, commit))
        return SimpleNamespace(id=1, name=item.name, description=item.description, level=item.level)

    async def update_feature_for_source(self, source_type, source_id, feature_id, fields, *, commit=False):
        self.updated.append((source_type, source_id, feature_id, fields, commit))
        return SimpleNamespace(
            id=feature_id,
            name=fields.get("name", "Extra Attack"),
            description=fields.get("description", ""),
            level=fields.get("level"),
        )

    async def delete_feature_for_source(self, source_type, source_id, feature_id, *, commit=False):
        self.deleted.append((source_type, source_id, feature_id, commit))
        return None

    async def invalidate(self):
        self.invalidate_calls += 1


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.feature_sync.reconcile_characters_for_source", AsyncMock())


def make_nested_service(db=None):
    db = db or FakeAsyncSession()
    service = NestedFeatureService(db)
    service._features = FakeFeatureCrudService(db)
    return service, db


def make_race_feature_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = RaceFeatureService(db)
    service.repository = FakeRepository(db, existing_by_id=existing_by_id, model=Race)
    service._features = FakeNestedFeatures(db)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestNestedFeatureService:
    async def test_fk_for_resolves_source_fk(self):
        service, _ = make_nested_service()

        assert service.fk_for(FeatureSourceType.CLASS) == "class_id"
        assert service.fk_for(FeatureSourceType.RACE) == "race_id"
        assert service.fk_for(FeatureSourceType.SUBRACE) == "subrace_id"
        assert service.fk_for(FeatureSourceType.BACKGROUND) == "background_id"
        assert service.fk_for(FeatureSourceType.FEAT) == "feat_id"
        assert service.fk_for(FeatureSourceType.SUBCLASS) == "subclass_id"

    async def test_fk_for_raises_for_unsupported_source(self):
        service, _ = make_nested_service()

        with pytest.raises(ValueError):
            service.fk_for(FeatureSourceType.OTHER)

    async def test_create_feature_for_source_delegates_to_feature_crud(self):
        service, _ = make_nested_service()
        data = NestedFeatureCreate(name="Keen Senses", description="d", level=None)

        feature = await service.create_feature_for_source(
            FeatureSourceType.RACE, 3, data, created_by_id=7, commit=False
        )

        assert feature.id == 1
        assert service._features.calls == [("create", FeatureSourceType.RACE, 3, data, 7, False)]

    async def test_create_features_for_source_delegates_to_feature_crud(self):
        service, _ = make_nested_service()
        data = [NestedFeatureCreate(name="Keen Senses", description="d", level=None)]

        features = await service.create_features_for_source(
            FeatureSourceType.RACE, 3, data, created_by_id=7, commit=False
        )

        assert [feature.id for feature in features] == [1]
        assert service._features.calls == [("create_many", FeatureSourceType.RACE, 3, data, 7, False)]

    async def test_update_feature_for_source_delegates_to_feature_crud(self):
        service, _ = make_nested_service()

        feature = await service.update_feature_for_source(
            FeatureSourceType.RACE, 3, 5, {"name": "Fey Ancestry"}, commit=False
        )

        assert feature.id == 5
        assert service._features.calls == [("update", FeatureSourceType.RACE, 3, 5, {"name": "Fey Ancestry"}, False)]

    async def test_delete_feature_for_source_delegates_to_feature_crud(self):
        service, _ = make_nested_service()

        result = await service.delete_feature_for_source(FeatureSourceType.RACE, 3, 5, commit=False)

        assert result is None
        assert service._features.calls == [("delete", FeatureSourceType.RACE, 3, 5, False)]


@pytest.mark.unit
@pytest.mark.asyncio
class TestSourceFeatureMixin:
    async def test_list_features_checks_source_and_lists(self):
        service, db = make_race_feature_service(existing_by_id={1: SimpleNamespace(id=1)})

        result = await service.list_features(1)

        assert result == []
        assert service._features.list_calls == [(FeatureSourceType.RACE, 1)]

    async def test_list_features_raises_when_source_missing(self):
        service, _ = make_race_feature_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.list_features(99)

    async def test_add_feature_creates_reconciles_and_invalidates(self):
        service, db = make_race_feature_service(existing_by_id={1: SimpleNamespace(id=1)})
        data = NestedFeatureCreate(name="Fey Ancestry", description="d", level=None)

        result = await service.add_feature(1, data, created_by_id=7)

        assert result.id == 1
        assert service._features.created == [(FeatureSourceType.RACE, 1, data, 7, False)]
        assert service._features.invalidate_calls == 1
        assert db.commits == 1

    async def test_update_feature_updates_in_place(self):
        service, db = make_race_feature_service(existing_by_id={1: SimpleNamespace(id=1)})

        result = await service.update_feature(1, 5, FeatureUpdate(name="Fey Ancestry"))

        assert result.id == 5
        assert service._features.updated == [(FeatureSourceType.RACE, 1, 5, {"name": "Fey Ancestry"}, False)]
        assert db.commits == 1

    async def test_remove_feature_deletes_and_reconciles(self):
        service, db = make_race_feature_service(existing_by_id={1: SimpleNamespace(id=1)})

        result = await service.remove_feature(1, 5)

        assert result is None
        assert service._features.deleted == [(FeatureSourceType.RACE, 1, 5, False)]
        assert db.commits == 1
