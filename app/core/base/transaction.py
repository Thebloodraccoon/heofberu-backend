"""
Transaction ownership helpers (Unit of Work style).

The rule for new code: **the service owns the transaction**. Repositories do
the writes, the service wraps a business operation in :func:`atomic` (or
:func:`unit_of_work`), and cache invalidation is scheduled with
:func:`invalidate_after_commit` so it can only ever run once the data is
durable. Repositories still accept the legacy ``commit=`` flag.

Cache purges and other side effects registered through :func:`after_commit`
inside an :func:`atomic` block run only after a successful ``COMMIT`` and are
dropped on rollback. Outside an ``atomic`` block (legacy ``commit=True``
flows, the repository already committed) they run immediately.
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


async def commit_or_rollback(db: AsyncSession) -> None:
    """Commit pending changes; roll back and re-raise if the commit fails."""

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def after_commit(db: AsyncSession, callback: AfterCommitCallback) -> None:
    """
    Run ``callback`` once the surrounding :func:`atomic` block has committed.

    Dropped if the block rolls back. When no ``atomic`` block is active the
    callback runs immediately: the legacy ``commit=True`` repository calls
    have already committed by then.
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

    Every repository write inside the block MUST pass ``commit=False``.
    Commits once on success and then runs the callbacks registered through
    :func:`after_commit`; rolls back, discards them and re-raises on any
    exception.
    """

    state = _state(db)
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
            await self.repository.create(data, commit=False)
            await uow.invalidate("spells")
    """

    async with atomic(db):
        yield UnitOfWork(db)
