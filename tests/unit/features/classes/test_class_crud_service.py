"""
Unit tests for ClassCrudService: create/update/delete orchestration (single
transaction, cache purges only after commit and only the namespaces that
changed) and ``get_by_id`` serialization of the class with its features and
subclasses.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, DiceType
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.classes.cache import CLASS_CRUD_CACHE_NAMESPACES, CLASS_DELETE_CACHE_NAMESPACES
from app.features.classes.crud.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.classes.crud.service import ClassCrudService
from app.features.classes.proficiencies.kinds import SAVING_THROWS
from tests.unit.fakes import FakeAsyncSession
from tests.unit.features.classes.helpers import FakeClassRepository, make_class_row, purged_namespaces


@pytest.fixture
def characters_purge(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.features.classes.crud.service.invalidate_characters_cache", mock)
    return mock


def make_crud_service(existing_by_id=None, **repository_kwargs):
    db = FakeAsyncSession()
    service = ClassCrudService(db)
    service.repository = FakeClassRepository(db, existing_by_id=existing_by_id, **repository_kwargs)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreate:
    async def test_create_class_persists_base_fields_and_purges_only_class_reads(self, purged):
        service, db = make_crud_service()

        result = await service.create_class(
            ClassCreate(name="Fighter", hit_dice=DiceType.D10, spellcasting_ability=None)
        )

        assert isinstance(result, ClassResponse)
        assert result.id == 1
        assert service.repository.created[0].name == "Fighter"
        assert db.commits == 1
        assert purged_namespaces(purged) == ["classes", "spells"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetById:
    async def test_get_by_id_serializes_features_and_subclasses_from_the_loaded_row(self):
        feature = SimpleNamespace(
            id=3,
            name="Fighting Style",
            description="d",
            level=1,
            choice_groups=[],
            static_groups=[],
            has_static_effects=False,
            has_choices=False,
            effects_summary="",
        )
        subclass = SimpleNamespace(id=2, class_id=1, name="Champion", image_url=None)
        row = make_class_row(features=[feature], subclasses=[subclass])
        service, db = make_crud_service(existing_by_id={1: row})

        result = await service.get_by_id(1)

        assert [f.id for f in result.features] == [3]
        assert [(s.id, s.name) for s in result.subclasses] == [(2, "Champion")]
        assert db.commits == 0

    async def test_get_by_id_raises_when_class_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_by_id(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdate:
    async def test_update_runs_row_and_saving_throws_in_one_commit(self, purged, characters_purge):
        row = make_class_row()
        service, db = make_crud_service(existing_by_id={1: row})

        result = await service.update_class(
            1, ClassUpdate(description="Martial archetype.", saving_throws=[AbilityScore.STR, AbilityScore.CON])
        )

        repository = service.repository
        assert repository.update_calls == [(row, {"description": "Martial archetype."})]
        assert repository.proficiency_calls == [(1, SAVING_THROWS, [AbilityScore.STR, AbilityScore.CON])]
        assert db.commits == 1
        assert result.description == "Martial archetype."
        assert purged_namespaces(purged) == ["classes", "spells"]
        characters_purge.assert_not_awaited()

    async def test_update_without_saving_throws_leaves_them_alone(self, purged):
        service, _ = make_crud_service(existing_by_id={1: make_class_row()})

        await service.update_class(1, ClassUpdate(name="Knight"))

        assert service.repository.proficiency_calls == []

    async def test_failure_in_second_step_rolls_back_and_purges_nothing(self, purged):
        service, db = make_crud_service(existing_by_id={1: make_class_row()})
        service.repository.fail_on_proficiencies = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await service.update_class(1, ClassUpdate(name="Knight", saving_throws=[AbilityScore.STR]))

        assert db.commits == 0
        assert db.rollbacks == 1
        assert purged.await_count == 0

    async def test_hit_dice_change_purges_only_that_classes_characters(self, purged, characters_purge):
        service, _ = make_crud_service(existing_by_id={1: make_class_row()}, character_ids=[7, 8])

        await service.update_class(1, ClassUpdate(hit_dice=DiceType.D12))

        characters_purge.assert_awaited_once_with([7, 8])

    async def test_unchanged_hit_dice_does_not_touch_character_cache(self, purged, characters_purge):
        service, _ = make_crud_service(existing_by_id={1: make_class_row(hit_dice=DiceType.D10)}, character_ids=[7])

        await service.update_class(1, ClassUpdate(hit_dice=DiceType.D10))

        characters_purge.assert_not_awaited()

    async def test_update_raises_when_class_missing(self, purged):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update_class(99, ClassUpdate(name="Knight"))

        assert purged.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestDelete:
    async def test_delete_purges_every_namespace_the_cascade_touches(self, purged):
        row = make_class_row()
        service, _ = make_crud_service(existing_by_id={1: row})

        assert await service.delete(1) is True

        assert service.repository.deleted == [row]
        assert purged_namespaces(purged) == list(CLASS_DELETE_CACHE_NAMESPACES)

    async def test_delete_in_use_purges_nothing(self, purged):
        service, _ = make_crud_service(existing_by_id={1: make_class_row()}, in_use=True)

        with pytest.raises(RecordInUseError):
            await service.delete(1)

        assert purged.await_count == 0

    async def test_delete_raises_when_class_missing(self, purged):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)


@pytest.mark.unit
class TestCacheNamespaces:
    def test_class_writes_do_not_purge_all_character_payloads(self):
        assert ClassCrudService.cache_namespaces == CLASS_CRUD_CACHE_NAMESPACES == ("classes", "spells")
        assert "characters" not in CLASS_DELETE_CACHE_NAMESPACES

    def test_delete_covers_cascaded_subclass_feature_item_and_spell_caches(self):
        assert {"classes", "class_features", "subclass_features", "features", "nested_items", "spells"} <= set(
            CLASS_DELETE_CACHE_NAMESPACES
        )
