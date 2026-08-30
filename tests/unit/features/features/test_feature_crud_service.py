"""
Unit tests for the central FeatureCrudService.

Covers the service bodies the integration tests through the HTTP layer do
not trace: source-scoped listing, any-source create, the level rules on
update, deletion, and the per-source cache-invalidation split behind the
``SOURCE_FEATURE_LIST_NAMESPACE`` map.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import FeatureSourceType
from app.core.exceptions import RecordNotFoundError
from app.features.features.crud.schemas import FeatureCreate, FeatureUpdate
from app.features.features.crud.service import SOURCE_FEATURE_LIST_NAMESPACE, FeatureCrudService
from app.features.features.exceptions import InvalidFeatureSourceException
from app.models.feature_model import Feature
from tests.unit.fakes import FakeAsyncSession, FakeRepository, FakeResult

_FK_BY_SOURCE = {
    FeatureSourceType.CLASS: "class_id",
    FeatureSourceType.SUBCLASS: "subclass_id",
    FeatureSourceType.RACE: "race_id",
    FeatureSourceType.SUBRACE: "subrace_id",
    FeatureSourceType.BACKGROUND: "background_id",
}


def make_feature(**overrides) -> SimpleNamespace:
    source_type = overrides.get("source_type", FeatureSourceType.CLASS)
    fk_name = _FK_BY_SOURCE.get(source_type)
    base = {
        "id": 1,
        "name": "Extra Attack",
        "source_type": source_type,
        "class_id": None,
        "subclass_id": None,
        "race_id": None,
        "subrace_id": None,
        "background_id": None,
        "level": 5 if source_type is not FeatureSourceType.OTHER else None,
        "description": "",
    }
    if fk_name is not None:
        base[fk_name] = 1
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeFeatureRepository(FakeRepository):
    """Feature repository stand-in (base fake already records create/update/delete)."""

    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Feature)


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Stop feature cache invalidation from touching Redis."""

    monkeypatch.setattr("app.features.features.crud.service.invalidate_feature_cache", AsyncMock())
    monkeypatch.setattr("app.features.features.crud.service.invalidate", AsyncMock())
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", AsyncMock())


def make_crud_service(existing_by_id=None, execute_results=None):
    db = FakeAsyncSession(execute_results=execute_results)
    service = FeatureCrudService(db)
    service.repository = FakeFeatureRepository(db, existing_by_id=existing_by_id)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudCreate:
    async def test_create_other_feature(self):
        service, db = make_crud_service()
        data = FeatureCreate(name="Gift", source_type=FeatureSourceType.OTHER, description="d")

        result = await service.create(data)

        assert result.id == 1
        assert result.name == "Gift"
        assert db.commits == 1

    async def test_create_source_owned_feature(self):
        service, db = make_crud_service()
        data = FeatureCreate(
            name="Keen Senses",
            source_type=FeatureSourceType.RACE,
            race_id=3,
            description="d",
        )

        result = await service.create(data)

        assert result.race_id == 3
        assert result.level is None

    async def test_create_source_owned_feature_reconciles_characters(self, monkeypatch):
        reconcile = AsyncMock()
        monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", reconcile)
        service, db = make_crud_service()

        await service.create(
            FeatureCreate(name="Keen Senses", source_type=FeatureSourceType.RACE, race_id=3, description="d")
        )

        reconcile.assert_awaited_once_with(db, FeatureSourceType.RACE, 3)

    async def test_create_other_skips_character_reconciliation(self, monkeypatch):
        reconcile = AsyncMock()
        monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", reconcile)
        service, _ = make_crud_service()

        await service.create(FeatureCreate(name="Gift", source_type=FeatureSourceType.OTHER, description="d"))

        reconcile.assert_not_awaited()

    async def test_create_invalidates_owning_catalog_list_and_parent_only(self, monkeypatch):
        invalidate_feature = AsyncMock()
        invalidate = AsyncMock()
        monkeypatch.setattr("app.features.features.crud.service.invalidate_feature_cache", invalidate_feature)
        monkeypatch.setattr("app.features.features.crud.service.invalidate", invalidate)
        service, _ = make_crud_service()

        await service.create(FeatureCreate(name="Fey", source_type=FeatureSourceType.SUBRACE, subrace_id=1, level=1))

        assert invalidate_feature.await_count == 1
        # only the subrace's own list namespace and its parent read namespace
        # are purged alongside the shared one — never a neighbor catalog
        assert SOURCE_FEATURE_LIST_NAMESPACE[FeatureSourceType.SUBRACE] == "subrace_features"
        assert sorted(call.args for call in invalidate.call_args_list) == [("races",), ("subrace_features",)]


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudListForSource:
    async def test_list_for_source_resolves_fk(self):
        rows = [make_feature(id=1, source_type=FeatureSourceType.CLASS, class_id=4, name="A", level=1)]
        service, db = make_crud_service(execute_results=[FakeResult(rows)])

        result = await service.list_for_source(FeatureSourceType.CLASS, 4)

        assert [item.name for item in result] == ["A"]
        assert len(db.executes) == 1

    async def test_list_for_source_other_raises(self):
        service, _ = make_crud_service()

        with pytest.raises(ValueError):
            await service.list_for_source(FeatureSourceType.OTHER, 1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudUpdate:
    async def test_update_renames_feature(self):
        feature = make_feature()
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(name="Legendary Action"))

        assert result.name == "Legendary Action"

    async def test_update_level_out_of_range_rejected(self):
        feature = make_feature()
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException):
            await service.update_feature(1, FeatureUpdate(level=25))

    async def test_update_class_level_cannot_be_cleared(self):
        feature = make_feature(source_type=FeatureSourceType.CLASS)
        service, _ = make_crud_service(existing_by_id={1: feature})

        with pytest.raises(InvalidFeatureSourceException):
            await service.update_feature(1, FeatureUpdate(level=None))

    async def test_update_race_level_optional_and_clearable(self):
        feature = make_feature(source_type=FeatureSourceType.RACE, race_id=2, level=1)
        service, _ = make_crud_service(existing_by_id={1: feature})

        result = await service.update_feature(1, FeatureUpdate(level=None))

        assert result.level is None

    async def test_update_reconciles_owning_source_characters(self, monkeypatch):
        reconcile = AsyncMock()
        monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", reconcile)
        service, db = make_crud_service(existing_by_id={1: make_feature()})

        await service.update_feature(1, FeatureUpdate(level=3))

        reconcile.assert_awaited_once_with(db, FeatureSourceType.CLASS, 1)

    async def test_update_raises_when_feature_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update_feature(99, FeatureUpdate(name="x"))


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatureCrudDelete:
    async def test_delete_any_source_feature(self):
        feature = make_feature(source_type=FeatureSourceType.BACKGROUND, background_id=7)
        service, db = make_crud_service(existing_by_id={1: feature})

        result = await service.delete(1)

        assert result is True
        assert service.repository.deleted == [feature]
        assert db.commits == 1

    async def test_delete_reconciles_owning_source_characters(self, monkeypatch):
        reconcile = AsyncMock()
        monkeypatch.setattr("app.features.features.crud.service.reconcile_characters_for_source", reconcile)
        service, db = make_crud_service(existing_by_id={1: make_feature()})

        await service.delete(1)

        reconcile.assert_awaited_once_with(db, FeatureSourceType.CLASS, 1)

    async def test_delete_raises_when_feature_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)
