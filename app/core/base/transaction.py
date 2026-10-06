"""
Transaction ownership helpers (Unit of Work style).

The rule for new code: **the service owns the transaction**. Repositories do
the writes (flush only, guarded by :func:`require_atomic`), the service wraps
every write in :func:`atomic` (or :func:`unit_of_work`), and cache invalidation
is scheduled with :func:`invalidate_after_commit` so it can only ever run once
the data is durable. There is no other commit path.

Cache purges and other side effects registered through :func:`after_commit`
inside an :func:`atomic` block run only after a successful ``COMMIT`` and are
dropped on rollback. Outside an ``atomic`` block there is nothing to wait for,
so they run immediately.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
import logging
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AfterCommitCallback = Callable[[], Awaitable[None]]

_STATE_KEY = "heof.transaction"
_FALLBACK_STATE: "WeakKeyDictionary[Any, dict[str, Any]]" = WeakKeyDictionary()


def _state(db: Any) -> dict[str, Any]:
    """Per-session bookkeeping (``AsyncSession.info``; weak map for session stand-ins)."""

    info = getattr(db, "info", None)
    if isinstance(info, dict):
        return info.setdefault(_STATE_KEY, {"depth": 0, "pending": []})

    try:
        return _FALLBACK_STATE.setdefault(db, {"depth": 0, "pending": []})
    except TypeError:
        return {"depth": 0, "pending": []}


def in_atomic(db: Any) -> bool:
    """Whether ``db`` is currently inside an :func:`atomic` block."""

    return _state(db)["depth"] > 0


def require_atomic(db: Any) -> None:
    """Raise unless ``db`` is inside an :func:`atomic` block: a repository write outside one would never commit."""

    if not in_atomic(db):
        raise RuntimeError("Repository writes must run inside atomic() / _atomic(); the service owns the transaction.")


async def after_commit(db: AsyncSession, callback: AfterCommitCallback) -> None:
    """
    Run ``callback`` once the surrounding :func:`atomic` block has committed.

    Dropped if the block rolls back. When no ``atomic`` block is active the
    callback runs immediately.
    """

    state = _state(db)
    if state["depth"] > 0:
        state["pending"].append(callback)
        return

    await callback()


async def invalidate_after_commit(db: AsyncSession, *namespaces: str, keys: Iterable[str] = ()) -> None:
    """Purge cache ``namespaces`` (and exact ``keys``) after commit; see :func:`after_commit`."""

    from app.core.cache.invalidation import invalidate, invalidate_many

    keys = list(keys)
    names = list(namespaces)

    async def _purge() -> None:
        if keys:
            await invalidate_many(names, keys)
            return
        for namespace in names:
            await invalidate(namespace)

    await after_commit(db, _purge)


async def _run_pending(state: dict[str, Any]) -> None:
    pending, state["pending"] = state["pending"], []
    for callback in pending:
        try:
            await callback()
        except Exception:
            logger.warning("After-commit callback failed", exc_info=True)


@asynccontextmanager
async def atomic(db: AsyncSession) -> AsyncGenerator[None, None]:
    """
    Wrap a multistep write on ``db`` in one all-or-nothing transaction.

    Commits once on success and then runs the callbacks registered through
    :func:`after_commit`; rolls back, discards them and re-raises on any
    exception. Re-entrant: a nested block joins the outer one, which owns the
    commit.
    """

    state = _state(db)
    if state["depth"] > 0:
        yield
        return

    state["depth"] += 1
    try:
        async with db.begin_nested():
            yield
        await db.commit()
    except Exception:
        state["pending"].clear()
        await db.rollback()
        raise
    finally:
        state["depth"] -= 1

    await _run_pending(state)


class UnitOfWork:
    """Handle yielded by :func:`unit_of_work`: registers post-commit side effects."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def invalidate(self, *namespaces: str, keys: Iterable[str] = ()) -> None:
        """Schedule a cache purge for after the commit."""

        await invalidate_after_commit(self.db, *namespaces, keys=keys)

    async def after_commit(self, callback: AfterCommitCallback) -> None:
        """Schedule an arbitrary coroutine callback for after the commit."""

        await after_commit(self.db, callback)


@asynccontextmanager
async def unit_of_work(db: AsyncSession) -> AsyncGenerator[UnitOfWork, None]:
    """
    :func:`atomic` that yields a :class:`UnitOfWork` for scheduling post-commit work.

    Example::

        async with unit_of_work(self.repository.db) as uow:
            await self.repository.create(data)
            await uow.invalidate("spells")
    """

    async with atomic(db):
        yield UnitOfWork(db)


class TransactionMixin:
    """
    ``_atomic()`` / ``_unit_of_work()`` for any class that owns writes.

    Uses ``self.db`` as the session; a host that keeps it elsewhere (e.g. ``self.repository.db``) overrides
    ``_tx_db``.
    """

    @property
    def _tx_db(self) -> AsyncSession:
        return self.db  # type: ignore[attr-defined, no-any-return]

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None, None]:
        """One all-or-nothing transaction; see :func:`atomic`."""

        async with atomic(self._tx_db):
            yield

    @asynccontextmanager
    async def _unit_of_work(self) -> AsyncGenerator[UnitOfWork, None]:
        """:meth:`_atomic` that yields a :class:`UnitOfWork` for scheduling post-commit work."""

        async with unit_of_work(self._tx_db) as uow:
            yield uow
