"""Unit tests for the feat schemas, repository name-conflict handling and service orchestration."""

from pydantic import ValidationError
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.base.transaction import atomic
from app.core.exceptions import RecordAlreadyExistsError, RecordInUseError, RecordNotFoundError
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.crud.schemas import FeatCreate, FeatUpdate
from app.features.feats.crud.service import FeatCrudService
from app.features.feats.exceptions import FeatPrerequisiteIncompleteError
from app.models.features.feature_model import Feature
from tests.unit.fakes import FakeAsyncSession, FakeRepository


class _Orig(Exception):
    def __init__(self, sqlstate):
        super().__init__("driver error")
        self.sqlstate = sqlstate


def integrity_error(sqlstate):
    return IntegrityError("INSERT ...", {}, _Orig(sqlstate))


class FlushFailsSession(FakeAsyncSession):
    def __init__(self, error, **kwargs):
        super().__init__(**kwargs)
        self.error = error

    async def flush(self):
        raise self.error


@pytest.fixture(autouse=True)
def purged(monkeypatch):
    calls: list[str] = []

    async def record(namespace):
        calls.append(namespace)

    monkeypatch.setattr("app.core.base.service.invalidate", record)
    return calls


@pytest.mark.unit
class TestFeatSchemas:
    def test_create_strips_the_name(self):
        assert FeatCreate(name="  Alert  ").name == "Alert"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    def test_create_rejects_bad_names(self, name):
        with pytest.raises(ValidationError):
            FeatCreate(name=name)

    @pytest.mark.parametrize("payload", [{"prerequisite_ability": "STR"}, {"prerequisite_minimum_score": 13}])
    def test_create_requires_the_prerequisite_pair(self, payload):
        with pytest.raises(ValidationError):
            FeatCreate(name="Half", **payload)

    def test_create_accepts_the_full_pair(self):
        feat = FeatCreate(name="Heavy Armor Master", prerequisite_ability="STR", prerequisite_minimum_score=13)

        assert feat.prerequisite_minimum_score == 13

    @pytest.mark.parametrize("score", [0, 31])
    def test_create_bounds_the_minimum_score(self, score):
        with pytest.raises(ValidationError):
            FeatCreate(name="Bad", prerequisite_ability="STR", prerequisite_minimum_score=score)

    @pytest.mark.parametrize("field", ["name", "description", "prerequisite_description"])
    def test_update_rejects_explicit_null(self, field):
        with pytest.raises(ValidationError):
            FeatUpdate(**{field: None})

    def test_update_allows_clearing_the_nullable_prerequisite(self):
        update = FeatUpdate(prerequisite_ability=None, prerequisite_minimum_score=None)

        assert update.model_dump(exclude_unset=True) == {
            "prerequisite_ability": None,
            "prerequisite_minimum_score": None,
        }


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatRepositoryNameConflict:
    async def test_unique_violation_on_create_becomes_record_already_exists(self):
        session = FlushFailsSession(integrity_error("23505"))
        repository = FeatRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            async with atomic(session):
                await repository.create({"name": "Alert"})

    async def test_unique_violation_on_update_becomes_record_already_exists(self):
        session = FlushFailsSession(integrity_error("23505"))
        repository = FeatRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            async with atomic(session):
                await repository.update(Feature(id=1, name="Old"), {"name": "Alert"})

    async def test_other_integrity_errors_are_not_masked(self):
        session = FlushFailsSession(integrity_error("23502"))
        repository = FeatRepository(session)

        with pytest.raises(IntegrityError):
            async with atomic(session):
                await repository.create({"name": "Alert"})

    async def test_delete_locks_the_feature_row_before_the_guard(self):
        session = FakeAsyncSession(scalar_results=[1])
        repository = FeatRepository(session)

        with pytest.raises(RecordInUseError):
            await repository.delete(Feature(id=5, name="Alert"))

        assert "FOR UPDATE" in str(session.executes[0])
        assert session.deleted == []


class FakeFeatRepository(FakeRepository):
    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Feature)
        self.row_calls = []
        self.full_calls = []

    async def get_row(self, model_id):
        self.row_calls.append(model_id)
        return self._rows.get(model_id)

    async def get_by_id(self, model_id):
        self.full_calls.append(model_id)
        return self._rows.get(model_id)


def feat_row(**overrides):
    base = {
        "id": 1,
        "name": "Alert",
        "description": "",
        "source_type": "FEAT",
        "prerequisite_ability": None,
        "prerequisite_minimum_score": None,
        "prerequisite_description": "",
        "min_level": None,
        "has_static_effects": False,
        "has_choices": False,
    }
    base.update(overrides)
    return Feature(**base)


def make_service(rows):
    db = FakeAsyncSession()
    service = FeatCrudService(db)
    service.repository = FakeFeatRepository(db, existing_by_id={row.id: row for row in rows})
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeatService:
    async def test_update_reads_the_bare_row_and_loads_the_tree_once(self, purged):
        service = make_service([feat_row()])

        result = await service.update(1, FeatUpdate(description="New"))

        assert result.description == "New"
        assert service.repository.row_calls == [1]
        assert service.repository.full_calls == [1]
        assert set(purged) == {"feats", "features"}

    async def test_update_missing_feat_raises_not_found(self):
        service = make_service([])

        with pytest.raises(RecordNotFoundError):
            await service.update(9, FeatUpdate(description="New"))

    async def test_update_setting_only_the_ability_is_refused(self):
        service = make_service([feat_row()])

        with pytest.raises(FeatPrerequisiteIncompleteError):
            await service.update(1, FeatUpdate(prerequisite_ability="STR"))

        assert service.repository.updated == []

    async def test_update_not_touching_the_prerequisite_ignores_legacy_half_pairs(self):
        service = make_service([feat_row(prerequisite_ability="STR")])

        result = await service.update(1, FeatUpdate(description="New"))

        assert result.description == "New"

    async def test_delete_uses_the_bare_row_without_loading_the_tree(self, purged):
        service = make_service([feat_row()])

        assert await service.delete(1) is True

        assert service.repository.row_calls == [1]
        assert service.repository.full_calls == []
        assert set(purged) == {"feats", "features"}

    async def test_delete_missing_feat_raises_not_found(self):
        service = make_service([])

        with pytest.raises(RecordNotFoundError):
            await service.delete(1)

    async def test_ensure_exists_is_scoped_by_the_repository(self):
        service = make_service([feat_row()])

        await service.ensure_exists(1)
        with pytest.raises(RecordNotFoundError):
            await service.ensure_exists(2)

    async def test_create_feat_persists_in_one_transaction_and_purges_after_commit(self, purged):
        db = FakeAsyncSession()
        service = FeatCrudService(db)
        repository = FakeFeatRepository(db)
        created = []

        async def create(payload):
            created.append(payload)
            row = feat_row(id=1, name=payload["name"])
            repository._rows[1] = row
            return row

        repository.create = create
        service.repository = repository

        result = await service.create_feat(FeatCreate(name="Alert"))

        assert result.name == "Alert"
        assert len(created) == 1
        assert db.commits == 1
        assert set(purged) == {"feats", "features"}


@pytest.mark.unit
def test_feat_service_namespaces_cover_the_shared_features_cache():
    assert FeatCrudService.cache_namespaces == ("feats", "features")
