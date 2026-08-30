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
├── exceptions.py          # AppError regime + data-layer exceptions + ErrorResponse
├── base/                  # Repository / service base classes
│   ├── repository.py      #   BaseRepository (model-generic CRUD)
│   ├── service.py         #   BaseService, Page, atomic()
│   ├── cached_service.py  #   CachedService (transparently cached reads)
│   └── nested_service.py  #   NestedCollectionService (cached FK-scoped listings)
├── cache/                 # Failsafe Redis caching
│   ├── client.py          #   raw get/set/delete ops via settings.get_redis()
│   ├── decorator.py       #   @use_cache
│   ├── invalidation.py    #   invalidate(namespace) / flush_all()
│   └── serialization.py   #   encode()/decode() for Pydantic values
├── handlers/              # Exception handlers, registered on the FastAPI app
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

`get_db` yields one `AsyncSession` per request; `DatabaseDep` is the typed
alias every feature's `dependencies.py` builds on. The session factory
(`SessionLocal`) lives in `app/settings`. This is also the dependency the
HTTP test client overrides.

### `exceptions.py`

One exception regime:

- **`AppError`** — base class for every *application* error. Subclasses
  declare a class-level `status_code` (plus optional `headers`/`details`)
  and pass a human-readable message to `super().__init__`
  (`GmAccessException`, `InvalidCredentialsException`, ...).
- **Data-layer exceptions** — plain `Exception`s kept feature-agnostic:
  `RecordNotFoundError`, `RecordAlreadyExistsError`,
  `RecordIdsInvalidError`, `RecordInUseError`. Each has exactly one
  handler in `handlers/data_layer.py`.
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
- `commit_or_flush(commit=...)` — rollback-safe commit, or flush when the
  caller owns the transaction inside `_atomic()`.
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
- Writes purge the service's `cache_namespaces` via `_invalidate_cache`.
- `resolve_ids` validates FK id lists → `RecordIdsInvalidError` (→ 400).
- `atomic(db)` / `BaseService._atomic()` wrap multistep writes in one
  all-or-nothing transaction; every inner write passes `commit=False`.
- `Page` is the generic `{items, total, page, size}` envelope;
  `paginate()` converts 1-indexed page/size into skip/limit.

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

- `client.py` — low-level operations (`cache_get`/`cache_set`,
  pattern/prefix deletion). All connections come from
  `settings.get_redis()` (pooled singleton); keys are prefixed
  `<CACHE_PREFIX>:<namespace>:...`. Only keys under the app prefix are
  ever deleted — JWT blacklist entries are untouched.
- `decorator.py` — `@use_cache(ttl=..., namespace=..., key_builder=...,
  skip_if=..., schema=..., cache_none=...)`. Cache keys combine namespace,
  function name, and a canonical rendering of the arguments (key-sorted
  dicts, `None`s dropped). The deserialization schema comes from the
  return annotation at decoration time, falling back to per-call
  resolution from the instance when the annotation is missing/unbound
  (the generic cached base methods).
- `invalidation.py` — `invalidate(namespace)` deletes every key under the
  namespace (called by services after each write); `flush_all()` clears
  everything under the app prefix.
- `serialization.py` — `encode`/`decode` round-trip Pydantic models and
  `Page[...]` envelopes through `model_dump_json`/`model_validate_json`;
  bare `list[Model]` schemas go through `TypeAdapter`; scalars through
  plain JSON.

### `handlers/`

Exception handlers registered on the app, in order (see
`handlers/__init__.py:ALL_HANDLERS`):

1. `app_error.py` — any `AppError` subclass → its own `status_code` and
   message in the standardized envelope. Registered first so application
   errors are matched here rather than by the generic HTTP handler.
2. `http.py` — FastAPI `HTTPException` and Starlette `HTTPException`
   (framework-level errors keep their semantics).
3. `validation.py` — Pydantic `ValidationError` → 422 with per-field
   details (`_to_json_safe` keeps non-serializable inputs from crashing
   the error payload itself).
4. `data_layer.py` — `RecordAlreadyExistsError` → 400,
   `RecordNotFoundError` → 404, `RecordIdsInvalidError` → 400,
   `RecordInUseError` → 409.
5. `database.py` — `SQLAlchemyError` → 500, with `IntegrityError`
   narrowed to 400 and a best-effort constraint-type message.
6. `unhandled.py` — catch-all `Exception` → 500 (must stay last).

Each module exports a `HANDLERS` list of `(exception_class, handler)`
pairs; `main` registers them in the order above.

### `security/password.py`

bcrypt hashing via passlib. The sync primitives (~100–300 ms of CPU)
are wrapped as async functions through `anyio.to_thread.run_sync`, so
login/register endpoints never block the event loop.

### `security/token.py`

JWT lifecycle: `create_access_token` / `create_refresh_token` mint tokens
with a unique `jti` claim (what makes per-token revocation possible);
`decode_token` verifies signature/expiry (raising `InvalidTokenException`);
`verify_token` / `verify_refresh_token` additionally check the required
`token_type` and return a `DecodedToken` (email, jti, remaining TTL).
Revocation is separate from verification: `blacklist_token(jti, ttl)`
writes a Redis key that lives exactly as long as the token would have,
and callers that care check `is_token_blacklisted(jti)` explicitly.
Auth *dependencies* (`TokenDep`, `CurrentUserDep`, ...) live in
`app/features/users/security.py`, keeping `core` free of feature imports.

## Conventions

- Python 3.10+, full type hints; layer strictly endpoint → service →
  repository → model.
- Multi-table writes go through `_atomic()` with `commit=False` inner
  writes; single writes end with `commit_or_flush(commit=True)`.
- Rich Google-style docstrings; ruff clean (line length 120, double
  quotes, no relative imports).
