"""Unit tests for the transaction-ownership helpers and deferred cache invalidation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel, ConfigDict
import pytest

from app.core.base.repository import BaseRepository
from app.core.base.service import BaseService
from app.core.base.transaction import (
    TransactionMixin,
    after_commit,
    atomic,
    in_atomic,
    invalidate_after_commit,
    require_atomic,
    unit_of_work,
)
from app.core.pagination import paginate
from tests.unit.fakes import FakeAsyncSession, FakeRepository


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str = ""


class Svc(BaseService):
    cache_namespaces = ("things",)


def make_service():
    db = FakeAsyncSession()
    service = Svc(
        repository=FakeRepository(db, existing_by_id={1: SimpleNamespace(id=1, name="a")}), response_schema=Schema
    )
    return service, db


@pytest.fixture
def purge(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr("app.core.base.service.invalidate", mock)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", mock)
    return mock


@pytest.mark.unit
@pytest.mark.asyncio
class TestAtomic:
    async def test_commits_once_on_success(self):
        db = FakeAsyncSession()

        async with atomic(db):
            assert in_atomic(db)

        assert db.commits == 1
        assert db.rollbacks == 0
        assert not in_atomic(db)

    async def test_rolls_back_and_reraises_on_error(self):
        db = FakeAsyncSession()

        with pytest.raises(RuntimeError):
            async with atomic(db):
                raise RuntimeError("boom")

        assert db.commits == 0
        assert db.rollbacks == 1
        assert not in_atomic(db)

    async def test_after_commit_callbacks_run_after_the_commit(self):
        db = FakeAsyncSession()
        order = []
        original_commit = db.commit

        async def commit():
            order.append("commit")
            await original_commit()

        db.commit = commit

        async def callback():
            order.append("callback")

        async with atomic(db):
            await after_commit(db, callback)
            assert order == []

        assert order == ["commit", "callback"]

    async def test_after_commit_callbacks_are_dropped_on_rollback(self):
        db = FakeAsyncSession()
        callback = AsyncMock()

        with pytest.raises(RuntimeError):
            async with atomic(db):
                await after_commit(db, callback)
                raise RuntimeError("boom")

        callback.assert_not_awaited()

    async def test_after_commit_outside_atomic_runs_immediately(self):
        db = FakeAsyncSession()
        callback = AsyncMock()

        await after_commit(db, callback)

        callback.assert_awaited_once()

    async def test_failing_callback_does_not_fail_the_transaction(self):
        db = FakeAsyncSession()

        async with atomic(db):
            await after_commit(db, AsyncMock(side_effect=RuntimeError("redis down")))

        assert db.commits == 1

    async def test_callbacks_run_once(self):
        db = FakeAsyncSession()
        callback = AsyncMock()

        async with atomic(db):
            await after_commit(db, callback)
        async with atomic(db):
            pass

        callback.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeferredInvalidation:
    async def test_invalidate_after_commit_waits_for_commit(self, purge):
        db = FakeAsyncSession()

        async with atomic(db):
            await invalidate_after_commit(db, "a", "b")
            purge.assert_not_awaited()

        assert [call.args for call in purge.await_args_list] == [("a",), ("b",)]

    async def test_invalidate_after_commit_with_keys_uses_one_batch(self, monkeypatch):
        batch = AsyncMock()
        monkeypatch.setattr("app.core.cache.invalidation.invalidate_many", batch)
        db = FakeAsyncSession()

        async with unit_of_work(db) as uow:
            await uow.invalidate("a", keys=["cache:x:1"])
            batch.assert_not_awaited()

        batch.assert_awaited_once_with(["a"], ["cache:x:1"])

    async def test_service_write_outside_atomic_purges_immediately(self, purge):
        service, _ = make_service()

        await service.update(1, Schema(name="b"))

        purge.assert_awaited_once_with("things")

    async def test_service_purge_inside_atomic_is_deferred_until_commit(self, purge):
        service, db = make_service()

        async with service._atomic():
            await service._invalidate_cache()
            purge.assert_not_awaited()

        purge.assert_awaited_once_with("things")
        assert db.commits == 1

    async def test_service_purge_inside_atomic_is_dropped_on_rollback(self, purge):
        service, _ = make_service()

        with pytest.raises(RuntimeError):
            async with service._unit_of_work():
                await service._invalidate_cache()
                raise RuntimeError("boom")

        purge.assert_not_awaited()


@pytest.mark.unit
class TestPaginate:
    def test_converts_page_and_size(self):
        assert paginate(3, 20) == (40, 20)

    def test_clamps_invalid_values(self):
        assert paginate(0, 0) == (0, 1)
        assert paginate(2, 10_000)[1] == 1000


@pytest.mark.unit
@pytest.mark.asyncio
class TestNestedAtomic:
    async def test_inner_block_joins_outer_and_only_outer_commits(self):
        db = FakeAsyncSession()

        async with atomic(db):
            async with atomic(db):
                pass
            assert db.commits == 0
            assert in_atomic(db)

        assert db.commits == 1
        assert not in_atomic(db)

    async def test_inner_error_rolls_back_through_the_outer_block(self):
        db = FakeAsyncSession()

        with pytest.raises(RuntimeError):
            async with atomic(db):
                async with atomic(db):
                    raise RuntimeError("boom")

        assert (db.commits, db.rollbacks) == (0, 1)

    async def test_mixin_atomic_uses_tx_db(self):
        db = FakeAsyncSession()

        class Host(TransactionMixin):
            @property
            def _tx_db(self):
                return db

        async with Host()._atomic():
            assert in_atomic(db)

        assert db.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRequireAtomic:
    async def test_raises_outside_atomic(self):
        with pytest.raises(RuntimeError):
            require_atomic(FakeAsyncSession())

    async def test_passes_inside_atomic(self):
        db = FakeAsyncSession()

        async with atomic(db):
            require_atomic(db)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRepositoryWritesNeedAtomic:
    async def test_flush_raises_outside_atomic(self):
        db = FakeAsyncSession()

        with pytest.raises(RuntimeError):
            await BaseRepository(Svc, db, search_fields=[]).flush()

        assert db.flushes == 0

    async def test_flush_inside_atomic_flushes(self):
        db = FakeAsyncSession()

        async with atomic(db):
            await BaseRepository(Svc, db, search_fields=[]).flush()

        assert db.flushes == 1

    async def test_update_flushes_without_committing_until_atomic_exits(self):
        db = FakeAsyncSession()
        row = SimpleNamespace(id=1, name="old")

        async with atomic(db):
            await BaseRepository(Svc, db, search_fields=[]).update(row, {"name": "new"})
            assert (db.flushes, db.commits) == (1, 0)

        assert row.name == "new"
        assert db.commits == 1

    async def test_update_raises_outside_atomic(self):
        db = FakeAsyncSession()

        with pytest.raises(RuntimeError):
            await BaseRepository(Svc, db, search_fields=[]).update(SimpleNamespace(id=1, name="old"), {"name": "new"})
