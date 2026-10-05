"""
Shared fakes for unit tests: async session, result, and repository stand-ins.

These stand in for SQLAlchemy ``AsyncSession`` / ``BaseRepository`` so service
logic can be exercised without a database. They are intentionally dumb: they
record calls and return configured rows, never touching SQL.
"""

from types import SimpleNamespace
from typing import Any


class FakeScalars:
    """Stand-in for ``AsyncScalarResult`` (``scalars()`` return value)."""

    def __init__(self, rows: list[Any]):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeResult:
    """Stand-in for a query ``Result``: scalars, single-row, or raw rows."""

    def __init__(self, rows: list[Any] | None = None):
        self._rows = rows or []

    def scalars(self):
        return FakeScalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def unique(self):
        return self

    def all(self):
        return self._rows


class FakeAsyncSession:
    """
    Minimal async context-manager session: savepoint/commit bookkeeping.

    ``execute`` returns a configurable queue of ``FakeResult`` objects (in
    call order) and falls back to an empty result when the queue is drained.
    """

    def __init__(self, execute_results: list[FakeResult] | None = None, scalar_results: list[Any] | None = None):
        self._execute_results = list(execute_results or [])
        self._scalar_results = list(scalar_results or [])
        self.executes: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.nested_enters = 0
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.refreshed: list[Any] = []

    async def __aenter__(self):
        self.nested_enters += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin_nested(self):
        """Mirror AsyncSession.begin_nested: sync, returns an async CM (self)."""
        return self

    async def execute(self, stmt, params=None):
        self.executes.append(stmt)
        return self._execute_results.pop(0) if self._execute_results else FakeResult([])

    async def scalar(self, stmt):
        return self._scalar_results.pop(0) if self._scalar_results else None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        self.flushes += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        return obj

    async def delete(self, obj):
        self.deleted.append(obj)

    def add(self, obj):
        self.added.append(obj)


class FakeRepository:
    """Generic CRUD repository stand-in keyed by id."""

    def __init__(self, db, existing_by_id: dict[int, Any] | None = None, model: Any = None):
        self.db = db
        self.model = model or SimpleNamespace(__name__="FakeModel")
        self._rows = dict(existing_by_id or {})
        self._next_id = max(self._rows) + 1 if self._rows else 1
        self.created: list[Any] = []
        self.updated: list[Any] = []
        self.deleted: list[Any] = []

    async def get_by_id(self, model_id: int):
        return self._rows.get(model_id)

    async def exists_by_id(self, model_id: int) -> bool:
        return model_id in self._rows

    async def create(self, payload: dict[str, Any]):
        row = SimpleNamespace(id=self._next_id, **payload)
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        return row

    async def update(self, db_obj, update_data: dict[str, Any], *, refresh: bool = False):
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.updated.append(db_obj)
        if refresh:
            await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, db_obj):
        self.deleted.append(db_obj)
        return True

    async def flush(self):
        await self.db.flush()


class FakeRedisPipeline:
    """Buffers commands and replays them against a :class:`FakeCacheRedis` on ``execute``."""

    def __init__(self, redis: "FakeCacheRedis"):
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def queue(*args, **kwargs):
            self._commands.append((name, args, kwargs))
            return self

        return queue

    async def execute(self):
        results = []
        for name, args, kwargs in self._commands:
            results.append(await getattr(self._redis, name)(*args, **kwargs))
        self._commands = []
        return results


class FakeCacheRedis:
    """
    In-memory stand-in for the async Redis surface the cache layer uses.

    Strings live in ``data`` (so ``fake.data == {...}`` assertions only see cache
    entries); index SETs live in ``sets``. ``set_calls`` records ``(key, value, ex)``,
    ``unlinked`` every key passed to ``unlink``/``delete``, and ``scans`` counts
    ``scan_iter`` calls (namespace invalidation must never scan).
    """

    def __init__(self):
        self.data: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}
        self.expiries: dict[str, int] = {}
        self.counters: dict[str, int] = {}
        self.set_calls: list[tuple[str, Any, int | None]] = []
        self.unlinked: list[str] = []
        self.scans = 0

    def pipeline(self, transaction: bool = True):
        return FakeRedisPipeline(self)

    async def get(self, key):
        if key in self.counters:
            return str(self.counters[key])
        return self.data.get(key)

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def persist(self, name):
        return self.expiries.pop(name, None) is not None

    async def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))
        self.data[key] = value
        return True

    async def sadd(self, name, *members):
        bucket = self.sets.setdefault(name, set())
        before = len(bucket)
        bucket.update(members)
        return len(bucket) - before

    async def srem(self, name, *members):
        bucket = self.sets.get(name, set())
        removed = len(bucket & set(members))
        bucket.difference_update(members)
        if not bucket:
            self.sets.pop(name, None)
        return removed

    async def smembers(self, name):
        return set(self.sets.get(name, set()))

    async def scard(self, name):
        return len(self.sets.get(name, set()))

    async def expire(self, name, seconds):
        self.expiries[name] = seconds
        return True

    async def rename(self, source, destination):
        if source not in self.sets:
            raise RuntimeError("ERR no such key")
        self.sets[destination] = self.sets.pop(source)
        return True

    async def unlink(self, *keys):
        removed = 0
        for key in keys:
            self.unlinked.append(key)
            if self.data.pop(key, None) is not None or self.sets.pop(key, None) is not None:
                removed += 1
        return removed

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            self.unlinked.append(key)
            if self.data.pop(key, None) is not None or self.sets.pop(key, None) is not None:
                removed += 1
        return removed

    async def scan_iter(self, match=None, count=100):
        import fnmatch

        self.scans += 1
        for key in [*self.data, *self.sets, *self.counters]:
            if match is None or fnmatch.fnmatchcase(key, match):
                yield key
