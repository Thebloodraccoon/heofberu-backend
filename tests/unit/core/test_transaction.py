"""Unit tests for the transaction-ownership helpers and deferred cache invalidation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel, ConfigDict
import pytest

from app.core.base.service import BaseService, paginate
from app.core.base.transaction import (
    after_commit,
    atomic,
    commit_or_rollback,
    in_atomic,
    invalidate_after_commit,
    unit_of_work,
)
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
class TestCommitOrRollback:
    async def test_commits(self):
        db = FakeAsyncSession()

        await commit_or_rollback(db)

        assert db.commits == 1

    async def test_rolls_back_on_any_exception(self):
        db = FakeAsyncSession()
        db.commit = AsyncMock(side_effect=ValueError("bad"))

        with pytest.raises(ValueError):
            await commit_or_rollback(db)

        assert db.rollbacks == 1


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
class TestRepositoryTransactionHelpers:
    async def test_commit_or_flush_rolls_back_on_any_exception(self):
        from app.core.base.repository import BaseRepository

        db = FakeAsyncSession()
        db.commit = AsyncMock(side_effect=ValueError("bad"))
        repository = BaseRepository(Svc, db, search_fields=[])

        with pytest.raises(ValueError):
            await repository.commit_or_flush()

        assert db.rollbacks == 1

    async def test_commit_or_flush_flushes_when_the_caller_owns_the_transaction(self):
        from app.core.base.repository import BaseRepository

        db = FakeAsyncSession()

        await BaseRepository(Svc, db, search_fields=[]).commit_or_flush(commit=False)

        assert db.flushes == 1
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRepositoryUpdateCommitFlag:
    async def test_update_with_commit_false_only_flushes(self):
        from app.core.base.repository import BaseRepository

        db = FakeAsyncSession()
        row = SimpleNamespace(id=1, name="old")

        await BaseRepository(Svc, db, search_fields=[]).update(row, {"name": "new"}, commit=False)

        assert row.name == "new"
        assert (db.flushes, db.commits) == (1, 0)

    async def test_update_commits_by_default(self):
        from app.core.base.repository import BaseRepository

        db = FakeAsyncSession()

        await BaseRepository(Svc, db, search_fields=[]).update(SimpleNamespace(id=1, name="old"), {"name": "new"})

        assert (db.flushes, db.commits) == (0, 1)
