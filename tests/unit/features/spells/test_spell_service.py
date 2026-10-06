"""Unit tests for SpellCrudService update/delete/listing and the name-dependent cache matrix."""

from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.spells.cache import (
    SPELL_CACHE_NAMESPACES,
    SPELL_NAME_DEPENDENT_NAMESPACES,
    spell_cache_namespaces,
)
from app.features.spells.crud.schemas import SpellUpdate
from tests.unit.fakes import FakeAsyncSession
from tests.unit.features.spells.test_availability_service import FakeSpellRepository, make_spell


@pytest.fixture
def purged(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.core.base.service.invalidate", mock)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", mock)
    return mock


def make_service(existing_by_id=None):
    from app.features.spells.crud.service import SpellCrudService

    db = FakeAsyncSession()
    service = SpellCrudService(db)
    repo = FakeSpellRepository(db, existing_by_id=existing_by_id)

    async def get_plain(spell_id):
        return repo._rows.get(spell_id)

    async def update(db_obj, update_data, *, refresh=False):
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        repo.updated.append(db_obj)
        await db.flush()
        return db_obj

    repo.get_plain = get_plain
    repo.update = update
    service.repository = repo
    return service, db


def namespaces(purged) -> set[str]:
    return {call.args[0] for call in purged.await_args_list}


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpellUpdateCachePurge:
    async def test_rename_purges_every_namespace_that_renders_the_spell_name(self, purged):
        service, db = make_service({1: make_spell(name="Fire Bolt")})
        commits_seen = []
        purged.side_effect = lambda namespace: commits_seen.append(db.commits)

        result = await service.update(1, SpellUpdate(name="Fire Dart"))

        assert result.name == "Fire Dart"
        assert namespaces(purged) == set(SPELL_CACHE_NAMESPACES) | set(SPELL_NAME_DEPENDENT_NAMESPACES)
        assert set(commits_seen) == {1}

    async def test_update_that_keeps_the_name_purges_only_spells(self, purged):
        service, _ = make_service({1: make_spell(name="Fire Bolt")})

        await service.update(1, SpellUpdate(description="New text"))

        assert namespaces(purged) == {"spells"}

    async def test_update_with_the_same_name_is_not_a_rename(self, purged):
        service, _ = make_service({1: make_spell(name="Fire Bolt")})

        await service.update(1, SpellUpdate(name="Fire Bolt"))

        assert namespaces(purged) == {"spells"}

    async def test_update_missing_spell_raises(self, purged):
        service, _ = make_service({})

        with pytest.raises(RecordNotFoundError):
            await service.update(9, SpellUpdate(description="x"))

        assert purged.await_count == 0

    async def test_failed_update_rolls_back_and_purges_nothing(self, purged):
        service, db = make_service({1: make_spell()})

        async def boom(*args, **kwargs):
            raise RuntimeError("x")

        service.repository.update = boom

        with pytest.raises(RuntimeError):
            await service.update(1, SpellUpdate(name="Other"))

        assert db.rollbacks == 1
        assert purged.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpellDelete:
    async def test_delete_uses_the_bare_row_and_purges_only_spells(self, purged):
        service, _ = make_service({1: make_spell()})

        assert await service.delete(1) is True

        assert [row.id for row in service.repository.deleted] == [1]
        assert namespaces(purged) == {"spells"}

    async def test_delete_missing_spell_raises(self, purged):
        service, _ = make_service({})

        with pytest.raises(RecordNotFoundError):
            await service.delete(5)

    async def test_in_use_spell_is_not_deleted_and_not_purged(self, purged):
        service, _ = make_service({1: make_spell()})

        async def in_use(db_obj):
            raise RecordInUseError(model_name="Spell", model_id=db_obj.id)

        service.repository.delete = in_use

        with pytest.raises(RecordInUseError):
            await service.delete(1)

        assert purged.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpellListing:
    async def test_listing_merges_availability_and_keeps_database_order(self):
        from app.features.spells.crud.service import SpellCrudService

        service = SpellCrudService(FakeAsyncSession())
        rows = [
            _Row({"id": 2, "name": "Alpha", "school": "EVOCATION", "level": "LEVEL_1"}),
            _Row({"id": 1, "name": "Beta", "school": "EVOCATION", "level": "CANTRIP"}),
        ]

        class Repo:
            async def count(self, **kwargs):
                return 2

            async def get_brief(self, *columns, **kwargs):
                return rows

            async def load_availability(self, ids):
                assert ids == [2, 1]
                return {2: {"available_classes": [{"id": 9, "name": "Zed"}, {"id": 3, "name": "Abe"}]}}

        service.repository = Repo()

        page = await SpellCrudService.get_all.__wrapped__(service, page=1, size=10)

        assert [item.id for item in page.items] == [2, 1]
        # the repository's SQL ORDER BY is the order: no Python re-sort
        assert [ref.name for ref in page.items[0].available_classes] == ["Zed", "Abe"]
        assert page.items[1].available_classes == []


class _Row(tuple):
    """Minimal ``Row`` stand-in: indexable like a tuple and exposing ``_mapping``."""

    def __new__(cls, mapping):
        row = super().__new__(cls, (mapping["id"],))
        row._mapping = mapping
        return row


@pytest.mark.unit
class TestCacheMatrix:
    def test_plain_write_touches_spells_only(self):
        assert spell_cache_namespaces() == ("spells",)

    def test_rename_adds_every_namespace_embedding_the_name(self):
        wide = spell_cache_namespaces(name_changed=True)

        assert wide[0] == "spells"
        for namespace in ("features", "feats", "class_features", "classes", "races", "backgrounds", "characters"):
            assert namespace in wide
