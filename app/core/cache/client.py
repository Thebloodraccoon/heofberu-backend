"""
Low-level Redis cache store.

All access goes through ``settings.get_redis()`` (the same async context
manager used by the JWT blacklist) so no connection lifecycle is managed
here. Every operation is wrapped in try/except: if Redis is down the cache
behaves as an always-miss cache and the request proceeds to the database.

Namespace invalidation never scans the keyspace. Every key written through
:func:`cache_set` is also recorded in a small Redis SET (the *index*) per
namespace, so ``invalidate("spells")`` is ``SMEMBERS`` + ``UNLINK`` + ``SREM``
over exactly the keys that belong to the namespace (members leave the index only
after their keys were unlinked, so a failed purge can simply be retried)::

    cache:spells:get_all:1=1        -> index  <prefix>:__idx:spells
    cache:characters:7:stats        -> indexes <prefix>:__idx:characters
                                               <prefix>:__idx:characters:7

Indexes exist for the first segment and the first two segments of a key, which
covers every namespace in use (``spells``, ``characters:7``). Deeper
namespaces are served by filtering the two-segment index. An index is capped
(``CACHE_INDEX_MAX_KEYS``); when it overflows its whole namespace is flushed,
so index memory stays bounded. Index keys live under the cache prefix, so
:func:`cache_flush_all` removes them too.

Indexes carry NO TTL on purpose: the Redis ``volatile-lru`` eviction policy
only evicts keys that have a TTL, so a data key can be evicted (a harmless miss)
but its index never is, and namespace invalidation always finds every live key.

Invalidation is never silently lost. A purge that cannot run (Redis error,
timeout) is remembered in-process (:class:`_PendingPurges`) and replayed before
the next cache operation of this process; while one is pending, every cache
operation that cannot replay it degrades to a miss / no-op instead of serving or
storing data. Purges ignore the circuit breaker (they are rare and must be
attempted). Every purge also bumps a global *epoch* counter, which lets a
cache-aside reader detect that an invalidation happened while it was reading the
database (see :func:`cache_epoch` and ``cache_set(..., epoch=...)``), so a stale
value fetched before a commit is never stored after the purge.

A small circuit breaker skips Redis for a few seconds after repeated failures
so a blackholed instance costs one timeout per window, not one per request.
"""

from collections.abc import Callable, Iterable
import logging
import time
from typing import Any

from app.settings import settings

logger = logging.getLogger(__name__)

_INDEX_SEGMENT = "__idx"
_EPOCH_SEGMENT = "__epoch"
_PENDING_MAX_KEYS = 5000
_UNLINK_CHUNK = 1000
_DEFAULT_INDEX_MAX_KEYS = 50_000
_BREAKER_THRESHOLD = 3
_BREAKER_OPEN_SECONDS = 5.0


def _redis_provider() -> Callable:
    """Return ``settings.get_redis`` so tests can monkeypatch the provider."""

    return settings.get_redis


def cache_enabled() -> bool:
    """Whether caching is globally enabled (``CACHE_ENABLED`` stage setting)."""

    try:
        return bool(getattr(settings, "CACHE_ENABLED", True))
    except Exception:
        return True


def cache_prefix() -> str:
    """
    Key prefix for all cached entries: ``CACHE_PREFIX`` plus, when set, ``:CACHE_VERSION``.

    Bump ``CACHE_VERSION`` on deploys that change cached payload shapes so old
    entries are never read again.
    """

    prefix = getattr(settings, "CACHE_PREFIX", "cache")
    version = getattr(settings, "CACHE_VERSION", "")
    return f"{prefix}:{version}" if version else prefix


def cache_ttl_default() -> int:
    """Default TTL in seconds (``CACHE_TTL_DEFAULT`` stage setting)."""

    return getattr(settings, "CACHE_TTL_DEFAULT", 86400)


def _index_max_keys() -> int:
    return getattr(settings, "CACHE_INDEX_MAX_KEYS", _DEFAULT_INDEX_MAX_KEYS)


class _CircuitBreaker:
    """Opens after consecutive Redis failures; resets when the Redis provider changes."""

    def __init__(self) -> None:
        self.failures = 0
        self.opened_at: float | None = None
        self._provider: Any = None

    def bind(self, provider: Any) -> None:
        if provider is not self._provider:
            self._provider = provider
            self.failures = 0
            self.opened_at = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= _BREAKER_OPEN_SECONDS:
            self.opened_at = None
            self.failures = _BREAKER_THRESHOLD - 1
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> bool:
        """Record a failure; returns whether the breaker just opened."""

        self.failures += 1
        if self.failures >= _BREAKER_THRESHOLD and self.opened_at is None:
            self.opened_at = time.monotonic()
            return True
        return False


class _PendingPurges:
    """
    Purges that could not run, replayed before the next cache operation.

    Bounded: past ``_PENDING_MAX_KEYS`` entries the exact lists collapse into one
    "flush everything" marker, so memory stays constant however long Redis is down.
    """

    def __init__(self) -> None:
        self.namespaces: set[str] = set()
        self.keys: set[str] = set()
        self.flush = False

    def __bool__(self) -> bool:
        return self.flush or bool(self.namespaces) or bool(self.keys)

    def add(self, namespaces: Iterable[str] = (), keys: Iterable[str] = (), *, flush: bool = False) -> None:
        self.flush = self.flush or flush
        self.namespaces.update(namespaces)
        self.keys.update(keys)
        if len(self.namespaces) + len(self.keys) > _PENDING_MAX_KEYS:
            self.flush = True
        if self.flush:
            self.namespaces.clear()
            self.keys.clear()

    def take(self) -> tuple[list[str], list[str], bool]:
        taken = (sorted(self.namespaces), sorted(self.keys), self.flush)
        self.namespaces, self.keys, self.flush = set(), set(), False
        return taken

    def clear(self) -> None:
        self.take()


_breaker = _CircuitBreaker()
_pending = _PendingPurges()


def _provider(*, force: bool = False) -> Callable | None:
    """
    The Redis provider, or ``None`` while the circuit breaker is open.

    ``force`` ignores the breaker: purges must be attempted even then. Switching
    the provider (only tests do) drops the breaker state and the pending purges.
    """

    provider = _redis_provider()
    if provider is not _breaker._provider:
        _pending.clear()
    _breaker.bind(provider)
    return provider if force or _breaker.allow() else None


def _record_failure(message: str, *args: Any) -> None:
    opened = _breaker.failure()
    logger.warning(message, *args, exc_info=opened or None)
    if opened:
        logger.error("Redis cache circuit opened for %.0fs after repeated failures", _BREAKER_OPEN_SECONDS)


def _epoch_key() -> str:
    return f"{cache_prefix()}:{_EPOCH_SEGMENT}"


def _index_names(key: str) -> list[str]:
    """Index set names a cache ``key`` belongs to (empty for keys outside the cache prefix)."""

    prefix = cache_prefix()
    if not key.startswith(f"{prefix}:"):
        return []

    segments = key[len(prefix) + 1 :].split(":")
    if len(segments) < 2:
        return []

    names = [f"{prefix}:{_INDEX_SEGMENT}:{segments[0]}"]
    if len(segments) >= 3:
        names.append(f"{prefix}:{_INDEX_SEGMENT}:{segments[0]}:{segments[1]}")

    return names


async def _purge_index(redis: Any, index_name: str, *, key_prefix: str | None = None) -> set[str]:
    """
    Delete the keys listed in ``index_name`` (optionally only those starting with ``key_prefix``).

    Members leave the index only after their keys were unlinked: if Redis fails
    half way the index still lists everything left, so the purge can be retried.
    Keys indexed concurrently are not seen here; the epoch check in
    :func:`cache_set` covers readers racing the purge. Returns the deleted keys.
    """

    members = [key for key in await redis.smembers(index_name) if key_prefix is None or key.startswith(key_prefix)]
    for start in range(0, len(members), _UNLINK_CHUNK):
        chunk = members[start : start + _UNLINK_CHUNK]
        await redis.unlink(*chunk)
        await redis.srem(index_name, *chunk)

    return set(members)


async def _purge_namespace(redis: Any, namespace: str) -> int:
    """Delete every cached key under ``<prefix>:<namespace>:*`` using the indexes."""

    prefix = cache_prefix()
    segments = namespace.split(":")
    top = f"{prefix}:{_INDEX_SEGMENT}:{segments[0]}"

    if len(segments) == 1:
        return len(await _purge_index(redis, top))

    second = f"{top}:{segments[1]}"
    if len(segments) == 2:
        removed = await _purge_index(redis, second)
    else:
        removed = await _purge_index(redis, second, key_prefix=f"{prefix}:{namespace}:")

    if removed:
        await redis.srem(top, *removed)

    return len(removed)


async def _scan_delete(redis: Any, pattern: str) -> None:
    epoch_key = _epoch_key()
    batch: list[str] = []
    async for key in redis.scan_iter(match=pattern, count=500):
        if key == epoch_key:
            continue
        batch.append(key)
        if len(batch) >= _UNLINK_CHUNK:
            await redis.unlink(*batch)
            batch = []
    if batch:
        await redis.unlink(*batch)


async def _drop_keys(redis: Any, keys: Iterable[str]) -> None:
    pipe = redis.pipeline(transaction=True)
    queued = False
    for key in dict.fromkeys(keys):
        pipe.unlink(key)
        for index_name in _index_names(key):
            pipe.srem(index_name, key)
        queued = True
    if queued:
        await pipe.execute()


async def _apply_purge(redis: Any, namespaces: Iterable[str], keys: Iterable[str], flush: bool) -> None:
    """Bump the epoch, then delete the namespaces / exact keys (or everything when ``flush``)."""

    await redis.incr(_epoch_key())

    if flush:
        await _scan_delete(redis, f"{cache_prefix()}:*")
        return

    for namespace in dict.fromkeys(namespaces):
        await _purge_namespace(redis, namespace)

    await _drop_keys(redis, keys)


async def _replay_pending(redis: Any) -> None:
    """Run the purges that failed earlier; on failure they stay pending and the error propagates."""

    if not _pending:
        return

    namespaces, keys, flush = _pending.take()
    try:
        await _apply_purge(redis, namespaces, keys, flush)
    except Exception:
        _pending.add(namespaces, keys, flush=flush)
        raise


async def _purge(namespaces: list[str], keys: list[str], *, flush: bool = False) -> None:
    """Run one purge (after replaying older failures); if Redis fails, remember it for a retry."""

    provider = _provider(force=True)
    try:
        async with provider() as redis:
            await _replay_pending(redis)
            await _apply_purge(redis, namespaces, keys, flush)
        _breaker.success()
    except Exception:
        _pending.add(namespaces, keys, flush=flush)
        _record_failure("Cache invalidation failed; it is retried before the next cache operation")
        logger.error(
            "Cache purge deferred (namespaces=%s, keys=%d, flush=%s); reads degrade to misses until it succeeds",
            namespaces,
            len(keys),
            flush,
        )


async def cache_epoch() -> str | None:
    """
    The current invalidation epoch, or ``None`` when Redis is unavailable.

    Cache-aside readers take it BEFORE reading the database and pass it to
    :func:`cache_set`, which refuses to keep a value if any purge ran in between.
    """

    if not cache_enabled():
        return None

    provider = _provider()
    if provider is None:
        return None

    try:
        async with provider() as redis:
            await _replay_pending(redis)
            value = await redis.get(_epoch_key())
        _breaker.success()
        return str(value or "")
    except Exception:
        _record_failure("Cache epoch read failed")
        return None


async def cache_get(key: str) -> Any:
    """Fetch a raw cached value; returns ``None`` on miss, Redis failure or an unreplayable pending purge."""

    if not cache_enabled():
        return None

    provider = _provider()
    if provider is None:
        return None

    try:
        async with provider() as redis:
            await _replay_pending(redis)
            value = await redis.get(key)
        _breaker.success()
        return value
    except Exception:
        _record_failure("Cache GET failed for %s", key)
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None, *, epoch: str | None = None) -> None:
    """
    Store a raw value with an optional TTL and index it; no-op when caching is disabled.

    With ``epoch`` (from :func:`cache_epoch`, taken before the value was computed)
    the value is dropped again if any purge ran since: it may predate the write
    that triggered that purge.
    """

    if not cache_enabled():
        return

    provider = _provider()
    if provider is None:
        return

    if ttl is None:
        ttl = cache_ttl_default()

    try:
        async with provider() as redis:
            await _replay_pending(redis)
            indexes = _index_names(key)
            pipe = redis.pipeline(transaction=True)
            pipe.set(key, value, ex=ttl)
            for index_name in indexes:
                pipe.sadd(index_name, key)
                pipe.persist(index_name)
            if indexes:
                pipe.scard(indexes[0])
            if epoch is not None:
                pipe.get(_epoch_key())
            results = await pipe.execute()

            if epoch is not None and str(results[-1] or "") != epoch:
                await _drop_keys(redis, [key])
            elif indexes:
                size = int(results[-2 if epoch is not None else -1])
                if size > _index_max_keys():
                    logger.warning("Cache index %s exceeded %d keys; flushing the namespace", indexes[0], size)
                    await _purge_index(redis, indexes[0])
        _breaker.success()
    except Exception:
        _record_failure("Cache SET failed for %s", key)


async def cache_delete_key(key: str) -> None:
    """Delete a single cache key and its index entries; a failed delete is retried (see module docs)."""

    await cache_delete_many([], [key])


async def cache_delete_prefix(namespace: str) -> None:
    """Delete every key under ``<prefix>:<namespace>:*`` (index based)."""

    await cache_delete_many([namespace])


async def cache_delete_many(namespaces: list[str], keys: list[str] | None = None) -> None:
    """
    Delete every key under several namespaces plus any exact ``keys`` over one
    Redis connection. Use this instead of looping the single-item helpers when
    one write invalidates many entries (e.g. every character granted a
    feature a GM just edited).
    """

    if not cache_enabled():
        return

    if not namespaces and not keys:
        return

    await _purge(list(namespaces), list(keys or []))


async def cache_flush_all() -> None:
    """
    Delete every cached entry (and every index) under ``<prefix>:*``.

    Other Redis data (e.g. the ``token_blacklist:*`` JWT revocations) is
    left untouched; the epoch counter is kept (and bumped). O(keyspace): only
    for administrative purges. A failed flush is retried like any purge.
    """

    if not cache_enabled():
        return

    await _purge([], [], flush=True)
