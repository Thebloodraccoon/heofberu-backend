# `app/core/` — Generic Building Blocks

Framework-agnostic infrastructure shared by every feature: the database
session dependency, the repository/service base classes, the Redis cache,
the unified exception regime with its handlers, and password/token
security helpers.

**Dependency rule:** `app/core` never imports from `app/features` or
`app/models` — features depend on core, never the reverse. The only
outbound imports are FastAPI/SQLAlchemy/Pydantic/Redis, `app/settings`,
and (inside `core`) sibling modules.

## Layout

```
app/core/
├── db.py                  # DatabaseDep — the async session dependency
├── db_errors.py           # public SQLSTATE helpers: sqlstate(), is_unique_violation(), constraint_name()
├── exceptions.py          # AppError regime + data-layer exceptions + ErrorResponse
├── types.py               # INT32_MAX and the shared bounded id types EntityId / EntityIdPath
├── base/                  # Repository / service base classes
│   ├── repository.py      #   BaseRepository (model-generic CRUD)
│   ├── service.py         #   BaseService, Page, paginate()
│   ├── transaction.py     #   atomic(), unit_of_work(), after_commit(), invalidate_after_commit()
│   ├── cached_service.py  #   CachedService (transparently cached reads)
│   └── nested_service.py  #   NestedCollectionService (cached FK-scoped listings)
├── cache/                 # Failsafe Redis caching
│   ├── client.py          #   raw get/set/delete ops, namespace key indexes, pending purges, epoch, circuit breaker
│   ├── decorator.py       #   @use_cache, build_cache_key()
│   ├── namespaces.py      #   CACHE_DEPENDENTS: which namespaces embed which entity (one dependency map)
│   ├── invalidation.py    #   invalidate(namespace) / invalidate_many() / flush_all()
│   └── serialization.py   #   encode()/decode() for Pydantic values
├── handlers/              # Exception handlers, registered on the FastAPI app
├── email/                 # SMTP password-reset mailer
├── storage/               # Supabase image storage
└── security/              # Password hashing + JWT create/verify/blacklist
```

## Request flow through this layer

```
endpoint (app/features/...)
  → service  (base/service.py, extends BaseService/CachedService)
    → repository  (extends BaseRepository)
      → SQLAlchemy model (app/models/)
```

Errors bubble up as exceptions and are converted to the standardized
JSON envelope by `handlers/`, so no feature ever raises or catches
`fastapi.HTTPException`.

## Files in detail

### `db.py`

`DatabaseDep` is the typed alias over `settings.get_db` (one `AsyncSession`
per request) that every feature's `dependencies.py` builds on. The session
factory (`SessionLocal`) and `get_db` live in `app/settings`; `settings.get_db`
is the dependency the HTTP test client overrides.

### `exceptions.py`

One exception regime:

- **`AppError`** — base class for every *application* error. Subclasses
  declare a class-level `status_code` (plus optional `headers`/`details`)
  and pass a human-readable message to `super().__init__`
  (`GmAccessException`, `InvalidCredentialsException`, ...).
- **Data-layer exceptions** — feature-agnostic `AppError` subclasses:
  `RecordNotFoundError` (404), `RecordAlreadyExistsError` (400),
  `RecordIdsInvalidError` (400), `RecordInUseError` (409). The single
  `AppError` handler serves them; `ServiceUnavailableError` (503) covers an
  unreachable backing service.
- **`ErrorResponse`** — the standardized payload shape
  (`{error: {type, message, status_code, timestamp, details?, request_id?}}`)
  used by all handlers.

### `base/repository.py`

`BaseRepository[ModelType]` — reusable model-generic CRUD on an
`AsyncSession`: `get_by_id` / `get_all` / `get_brief` / `count` /
`create` / `update` / `delete`, plus shared patterns:

- constructor knobs: `default_load_options` (eager loading),
  `search_fields` (ILIKE substring search), `unique_fields`
  (pre-insert/update uniqueness checks → `RecordAlreadyExistsError`),
  `check_in_use_on_delete` (delete guard → `RecordInUseError`; requires an
  `is_in_use` override).
- `commit_or_flush(commit=...)` — rollback-safe commit (rolls back on any
  exception), or flush when the caller owns the transaction inside
  `_atomic()`. The old module-level `_commit_or_rollback(db)` is a deprecated
  alias of `base.transaction.commit_or_rollback`.
- `get_all` / `get_brief` order by the requested column(s) with `id` as the
  final tie-break, so OFFSET/LIMIT pages are deterministic.
- batch association helpers: `replace_association` (M2M tables) and
  `replace_child_rows` (child-row sets), both `commit=False`-aware.
- `exists_referencing` / `get_many_by_ids` — FK-existence and id-IN
  lookups defined once for reuse.

### `base/service.py`

The "fetch → validate → persist → serialize" orchestrator:

- `BaseService` wires a repository to response schemas and implements
  paginated `get_all` (with a column-select fast path when a lightweight
  `get_all_schema` is declared and it has no relationship fields),
  `get_by_id`, `create`, partial `update` (`exclude_unset=True`),
  `delete`.
- Writes purge the service's `cache_namespaces` via `_invalidate_cache`
  (deferred until after `COMMIT` inside `_atomic()` / `_unit_of_work()`).
- `resolve_ids` validates FK id lists → `RecordIdsInvalidError` (→ 400).
- `Page` is the generic `{items, total, page, size}` envelope;
  `paginate()` converts 1-indexed page/size into skip/limit (clamped to
  `1 <= size <= MAX_PAGE_SIZE`).

### `base/transaction.py`

The one transaction-ownership mechanism: **the service owns the
transaction**, repositories only write.

- `atomic(db)` / `BaseService._atomic()` — one all-or-nothing transaction
  (savepoint + commit); every inner write passes `commit=False`. Callbacks
  registered with `after_commit` run after the `COMMIT` and are dropped on
  rollback.
- `unit_of_work(db)` / `BaseService._unit_of_work()` — the same, yielding a
  `UnitOfWork` with `await uow.invalidate("ns", keys=[...])` and
  `await uow.after_commit(coro_fn)`.
- `invalidate_after_commit(db, *namespaces, keys=())` — outside an atomic
  block it purges immediately (the legacy `commit=True` repository call
  already committed).
- `commit_or_rollback(db)` — public replacement for the old private helper.

```python
async with self._unit_of_work() as uow:
    race = await self.repository.create(data, commit=False)
    await self.skills_repo.set_skills(race.id, skills, commit=False)
    await uow.invalidate("races", "characters")   # runs only after COMMIT
```

### `base/cached_service.py`

`CachedService` — reference-catalog services (races, classes, spells, ...)
extend this instead of re-declaring cached `get_all`/`get_by_id` overrides.
Because the return annotations carry unbound TypeVars, `@use_cache`
resolves the deserialization schema per call from the concrete instance
(`get_all_schema` wrapped in `Page[...]`, `response_schema` for detail
reads). A subclass only declares `cache_namespaces`.

### `base/nested_service.py`

`NestedCollectionService` — the shared read half of the per-source nested
collections ("all features/items of race X"): a cached
`SELECT * WHERE <fk> = source_id ORDER BY id`. Subclasses set `model`,
`response_schema`, `cache_namespaces` and implement `fk_for(source_type)`
to map a source type to its FK column. Writes stay domain-specific (see
`app/features/shared/{features,items}/nested_service.py`).

### `cache/`

Failsafe, transparent Redis caching. Any Redis failure degrades to a
cache miss / no-op — it never raises into business code. Disabled
globally with `CACHE_ENABLED=False`.

- `client.py` — low-level operations (`cache_get`/`cache_set`/
  `cache_delete_key`/`cache_delete_many`/`cache_epoch`). All connections come from
  `settings.get_redis()` (pooled singleton); keys are prefixed
  `<CACHE_PREFIX>[:<CACHE_VERSION>]:<namespace>:...`. `cache_set` also
  records the key in a per-namespace Redis SET (first segment and first two
  segments of the key), so namespace invalidation is `SMEMBERS` +
  `UNLINK` + `SREM` over exactly that namespace (members leave the index
  only after their keys are unlinked) — no keyspace `SCAN` (only the admin
  `flush_all` scans). An index is capped by `CACHE_INDEX_MAX_KEYS`; on
  overflow its namespace is flushed. Indexes have NO TTL: with the
  `volatile-lru` Redis policy only keys with a TTL are evicted, so an index
  is never evicted before its data keys (do not switch to `allkeys-*`).
  Guarantees around failures:
  - A purge that cannot run (Redis error/timeout, open breaker) is kept in
    an in-process bounded `_PendingPurges` and replayed before the next
    cache operation of that process; while it is pending every get/set
    degrades to a miss/no-op, so stale entries are never served or stored
    after an outage. Purges ignore the circuit breaker. Residual risk: a
    process that dies with a pending purge, or a different worker whose own
    Redis calls kept working, can serve the stale entry until its TTL.
  - Every purge bumps a global epoch counter (`<prefix>:__epoch`, no TTL).
    `@use_cache` reads the epoch before running the function and stores
    the result with `cache_set(..., epoch=...)`, which drops the value if a
    purge ran meanwhile (cache-aside refill race).
  - A circuit breaker skips Redis for 5 s after 3 consecutive failures. JWT
    blacklist and rate-limit keys are never touched.
- `decorator.py` — `@use_cache(ttl=..., namespace=..., key_builder=...,
  skip_if=..., schema=..., cache_none=...)`. Cache keys combine namespace,
  function name, and a canonical rendering of the arguments bound against
  the signature (`get(5)` and `get(item_id=5)` share a key; key-sorted
  dicts, `None`s dropped, long values such as search text replaced by a
  digest). `build_cache_key(func, *args, namespace=..., **kwargs)` returns
  the exact key for point invalidation. A cached payload that fails to
  decode is a miss (key dropped). The deserialization schema comes from the
  return annotation at decoration time, falling back to per-call
  resolution from the instance when the annotation is missing/unbound
  (the generic cached base methods).
- `namespaces.py` — `CACHE_DEPENDENTS` (+ `dependents(entity)`): the single
  declaration of which cached namespaces embed which entity's names/ids
  (skills, items, spell names, classes, races, tags, ...). The per-feature
  `cache.py` modules derive their purge sets from it;
  `tests/unit/core/test_cache_namespace_graph.py` fails when a cached namespace
  has no purge path or the map names a namespace nothing caches.
- `invalidation.py` — `invalidate(namespace)` / `invalidate_many(...)` delete
  every key under the namespace(s); `flush_all()` clears everything under
  the app prefix.
- `serialization.py` — `encode`/`decode` round-trip Pydantic models and
  `Page[...]` envelopes through `model_dump_json`/`model_validate_json`;
  bare `list[Model]` schemas go through `TypeAdapter`; scalars through
  plain JSON.

### `handlers/`

Exception handlers registered on the app, in order (see
`handlers/__init__.py:ALL_HANDLERS`):

1. `app_error.py` — any `AppError` subclass (including the `Record*`
   data-layer errors) → its own `status_code` and message in the
   standardized envelope. Registered first.
2. `http.py` — Starlette `HTTPException` (FastAPI's subclasses it), headers
   preserved (`Allow`, `WWW-Authenticate`).
3. `validation.py` — FastAPI `RequestValidationError` and Pydantic
   `ValidationError` → 422 envelope with `details.validation_errors`
   (`field`/`message`/`type`). The submitted `input` is never returned or
   logged.
4. `database.py` — `SQLAlchemyError` → 500; `IntegrityError` → 400 with a
   message chosen from the PostgreSQL SQLSTATE (23505/23503/23502/23514);
   pool exhaustion → 503. SQL and parameters are never logged or returned.
5. `unhandled.py` — catch-all `Exception` → 500 (must stay last).

`_response.py` holds the single `build_error_response(request, ...)` builder
every handler uses. Each module exports a `HANDLERS` list of
`(exception_class, handler)` pairs; `main` registers them in the order above.

### `security/password.py`

bcrypt hashing via passlib. The sync primitives (~100–300 ms of CPU)
are wrapped as async functions through `anyio.to_thread.run_sync`, so
login/register endpoints never block the event loop.

### `security/token.py`

JWT lifecycle: `create_access_token` / `create_refresh_token` mint tokens
with a unique `jti` claim (what makes per-token revocation possible);
`decode_token` verifies signature/expiry (raising `InvalidTokenException`);
`verify_token` / `verify_refresh_token` additionally check the required
`token_type` and return a `DecodedToken` (`subject`, jti, remaining TTL,
`issued_at_ms`). Tokens carry `iat` (s) and `iat_ms` claims; `blacklist_key(jti)`
is the public Redis key helper.
Revocation is separate from verification: `blacklist_token(jti, ttl)`
writes a Redis key that lives exactly as long as the token would have,
and callers that care check `is_token_blacklisted(jti)` explicitly. Redis
failures there fail closed with `ServiceUnavailableError` (503).
Auth *dependencies* (`TokenDep`, `CurrentUserDep`, role guards) and session
rules (revocation, single-use claims) live in `app/features/auth`, keeping
`core` free of feature imports and business rules.

## Conventions

- Python 3.10+, full type hints; layer strictly endpoint → service →
  repository → model.
- Multi-table writes go through `_atomic()` / `_unit_of_work()` with
  `commit=False` inner writes; single writes end with
  `commit_or_flush(commit=True)`. Cache purges inside a transaction go through
  `invalidate_after_commit` / `uow.invalidate`.
- Rich Google-style docstrings; ruff clean (line length 120, double
  quotes, no relative imports).
