# app/settings/

Application configuration and runtime wiring: environment-driven settings,
per-stage modules, the async SQLAlchemy engine/session factory, and the
pooled Redis client accessor.

## Layout

- `config.py` — `AppSettings` (pydantic-settings): loads env vars /
  `.env` (DB/Redis URLs, JWT, admin bootstrap, cache flags). Rejects the
  placeholder JWT secret outside dev/test at startup.
- `_common.py` — stage-independent building blocks:
  - flattened setting constants (`DATABASE_URL`, `CACHE_ENABLED`, ...),
  - `utcnow()` (naive UTC for `TIMESTAMP WITHOUT TIME ZONE` columns),
  - `as_async_database_url()` (sync URL → asyncpg form),
  - `make_async_session_factory` / `make_get_db` (FastAPI session dependency),
  - `make_get_redis(redis_url)` → `get_redis()`.
- `base.py` — the single declarative `Base` shared by all ORM models.
- `dev.py` / `test.py` / `prod.py` — per-stage modules selected by the
  `STAGE` env var in `__init__.py`; each exposes `engine`, `SessionLocal`,
  `get_db`, `get_redis`, `ALLOWED_HOSTS`, and pool tuning. The test stage
  always targets the isolated `TEST_*` URLs and disables the cache by
  default.

## `settings.get_redis()` semantics

Redis access is pooled: `get_redis()` is an async context manager yielding
a lazily created, process-wide **singleton** client — one connection pool
per process instead of a fresh TCP connect per operation. It does NOT
close the client on exit. If the running event loop differs from the loop
the client was created on (e.g. a new loop per test case), the client is
rebuilt automatically. Never open a fresh connection per operation.
