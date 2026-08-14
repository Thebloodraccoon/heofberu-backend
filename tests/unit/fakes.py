"""Shared fakes for unit tests: async session, result, and repository stand-ins.

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

    def all(self):
        return self._rows


class FakeAsyncSession:
    """Minimal async context-manager session: savepoint/commit bookkeeping.

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

    async def create(self, payload: dict[str, Any], *, commit: bool = True):
        row = SimpleNamespace(id=self._next_id, **payload)
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        if commit:
            await self.db.commit()
        return row

    async def update(self, db_obj, update_data: dict[str, Any], *, refresh: bool = False):
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.updated.append(db_obj)
        if refresh:
            await self.db.refresh(db_obj)
        else:
            await self.db.commit()
        return db_obj

    async def delete(self, db_obj):
        self.deleted.append(db_obj)
        return True
