"""Unit tests for SubclassCrudService: create/delete orchestration, cache scope, listing, schemas."""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.subclasses.cache import SUBCLASS_CRUD_CACHE_NAMESPACES, SUBCLASS_DELETE_CACHE_NAMESPACES
from app.features.subclasses.crud.schemas import SubclassCreate, SubclassUpdate
from app.features.subclasses.crud.service import SubclassCrudService
from app.features.subclasses.features.service import SubclassFeatureService
from tests.unit.fakes import FakeAsyncSession, FakeRepository
from tests.unit.features.classes.helpers import purged_namespaces


class FakeSubclassRepository(FakeRepository):
    def __init__(self, db, existing_by_id=None, *, in_use=False):
        from app.models.classes.subclass_model import Subclass

        super().__init__(db, existing_by_id=existing_by_id, model=Subclass)
        self.in_use = in_use
        self.listed: list = []
        self.list_calls: list = []

    async def get_row(self, subclass_id):
        return self._rows.get(subclass_id)

    async def delete(self, db_obj):
        if self.in_use:
            raise RecordInUseError(model_name="Subclass", model_id=db_obj.id)
        return await super().delete(db_obj)

    async def list_for_class(self, class_id=None):
        self.list_calls.append(class_id)
        return self.listed


def make_subclass_row(**overrides) -> SimpleNamespace:
    base = {"id": 1, "class_id": 1, "name": "Champion", "description": "", "image_url": None, "features": []}
    base.update(overrides)
    return SimpleNamespace(**base)


def make_service(existing_by_id=None, known_classes=(1,), **kwargs):
    db = FakeAsyncSession()
    service = SubclassCrudService(db)
    service.repository = FakeSubclassRepository(db, existing_by_id=existing_by_id, **kwargs)
    service._class_repository = FakeRepository(
        db, existing_by_id={cid: SimpleNamespace(id=cid) for cid in known_classes}
    )
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreate:
    async def test_create_persists_once_purges_classes_and_returns_the_full_response(self, purged):
        service, db = make_service()

        result = await service.create_subclass(SubclassCreate(name="Champion", class_id=1))

        assert service.repository.created[0].name == "Champion"
        assert (result.id, result.class_id, result.features) == (1, 1, [])
        assert db.commits == 1
        assert purged_namespaces(purged) == list(SUBCLASS_CRUD_CACHE_NAMESPACES) == ["classes", "spells"]

    async def test_create_for_unknown_class_raises_without_writing(self, purged):
        service, db = make_service(known_classes=())

        with pytest.raises(RecordNotFoundError):
            await service.create_subclass(SubclassCreate(name="Champion", class_id=9))

        assert service.repository.created == []
        assert purged.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetById:
    async def test_features_come_from_the_loaded_row(self):
        feature = SimpleNamespace(
            id=2,
            name="Improved Critical",
            description="",
            level=3,
            choice_groups=[],
            static_groups=[],
            has_static_effects=False,
            has_choices=False,
            effects_summary="",
        )
        service, _ = make_service(existing_by_id={1: make_subclass_row(features=[feature])})

        result = await service.get_by_id(1)

        assert [f.name for f in result.features] == ["Improved Critical"]

    async def test_missing_subclass_raises(self):
        service, _ = make_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_by_id(5)


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdate:
    async def test_update_applies_fields_purges_classes_and_returns_features(self, purged):
        feature = NestedFeatureResponse(id=2, name="F", description="", level=3)
        row = make_subclass_row(features=[feature])
        service, _ = make_service(existing_by_id={1: row})

        result = await service.update(1, SubclassUpdate(name="Battle Master"))

        assert result.name == "Battle Master"
        assert [f.id for f in result.features] == [2]
        assert purged_namespaces(purged) == ["classes", "spells"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestDelete:
    async def test_delete_purges_cascaded_feature_caches(self, purged):
        row = make_subclass_row()
        service, _ = make_service(existing_by_id={1: row})

        assert await service.delete(1) is True

        assert service.repository.deleted == [row]
        assert purged_namespaces(purged) == list(SUBCLASS_DELETE_CACHE_NAMESPACES)
        assert {"subclass_features", "features"} <= set(SUBCLASS_DELETE_CACHE_NAMESPACES)

    async def test_delete_in_use_purges_nothing(self, purged):
        service, _ = make_service(existing_by_id={1: make_subclass_row()}, in_use=True)

        with pytest.raises(RecordInUseError):
            await service.delete(1)

        assert purged.await_count == 0

    async def test_delete_missing_raises(self, purged):
        service, _ = make_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestListForClass:
    async def test_unknown_class_raises_404(self):
        service, _ = make_service(known_classes=(1,))

        with pytest.raises(RecordNotFoundError):
            await service.list_for_class(9)

        assert service.repository.list_calls == []

    async def test_lists_brief_rows_for_a_known_class(self):
        service, _ = make_service(known_classes=(1,))
        service.repository.listed = [SimpleNamespace(id=2, class_id=1, name="Champion", image_url=None)]

        result = await service.list_for_class(1)

        assert [(s.id, s.name) for s in result] == [(2, "Champion")]
        assert service.repository.list_calls == [1]

    async def test_without_class_id_lists_everything_and_skips_the_class_check(self):
        service, _ = make_service(known_classes=())

        await service.list_for_class(None)

        assert service.repository.list_calls == [None]


@pytest.mark.unit
class TestSchemas:
    @pytest.mark.parametrize("payload", [{"name": ""}, {"name": "x" * 101}, {"name": "A", "class_id": 0}])
    def test_create_rejects_bad_values(self, payload):
        with pytest.raises(ValidationError):
            SubclassCreate(**{"name": "A", "class_id": 1, **payload})

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "/img.png"])
    def test_create_rejects_non_http_image_url(self, url):
        with pytest.raises(ValidationError):
            SubclassCreate(name="A", class_id=1, image_url=url)

    @pytest.mark.parametrize("field", ["name", "description"])
    def test_update_rejects_explicit_null(self, field):
        with pytest.raises(ValidationError, match="cannot be null"):
            SubclassUpdate(**{field: None})

    def test_update_rejects_empty_and_overlong_name(self):
        with pytest.raises(ValidationError):
            SubclassUpdate(name="")
        with pytest.raises(ValidationError):
            SubclassUpdate(name="x" * 101)

    def test_update_keeps_only_sent_fields(self):
        assert SubclassUpdate(description="d").model_dump(exclude_unset=True) == {"description": "d"}


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubclassFeatureService:
    async def test_lists_subclass_source_features_and_404s_for_unknown_subclass(self):
        db = FakeAsyncSession()
        service = SubclassFeatureService(db)
        service.repository = FakeSubclassRepository(db, existing_by_id={1: make_subclass_row()})
        calls = []

        async def list_for_source(source_type, source_id):
            calls.append((source_type.value, source_id))
            return []

        service._features.list_for_source = list_for_source

        assert await service.list_features(1) == []
        assert calls == [("SUBCLASS", 1)]

        with pytest.raises(RecordNotFoundError):
            await service.list_features(9)
