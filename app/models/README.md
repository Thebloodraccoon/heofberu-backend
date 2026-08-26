# app/models/

SQLAlchemy 2.0 ORM models — one file per domain, plus shared column-type
enums. Everything here maps directly onto Postgres tables managed by
Alembic migrations (the models never create or alter schema themselves).

## Layout

- `enums.py` — SQLAlchemy `Enum` column types (`UserRoleType`,
  `AbilityScoreType`, ...) mapped from the domain enums in
  `app/constants.py`. All are native Postgres ENUMs created with
  `create_type=False`: the actual `CREATE TYPE` statements live in the
  Alembic migrations.
- `<domain>_model.py` — one file per domain (`user_model.py`,
  `character_model.py`, `class_model.py`, ...). Association/M2M tables and
  composite-PK sub-resources live in `<domain>_association_models.py`.
- `__init__.py` — re-exports every model so a single
  `import app.models` registers all tables on the shared metadata.

## Conventions

- Every model inherits `settings.Base` from `app/settings/base.py`
  (one declarative base for the whole app).
- **Import order in `__init__.py` is deliberate** — FK targets must be
  registered before dependents (e.g. `Subclass` after `Class`, `Feature`
  after all of its sources). Do not reorder imports there.
- Table, column, and class names are DB-facing and imported across the
  whole codebase — never rename them.
- Shared value enums live in `app/constants.py`; only the column-type
  wrappers live in `enums.py`.

## Related bootstrap & shared files

- `app/main.py` — application entrypoint: builds the FastAPI `app`
  (docs disabled in prod), registers middleware via `MiddlewareConfig`,
  installs the global error handlers, mounts `api_router`, and runs an
  Alembic-only lifespan (no DDL at startup).
- `app/router.py` — aggregates every feature router under the `/api`
  prefix; the import/include order is fixed.
- `app/constants.py` — app-wide domain enums (`AbilityScore`,
  `SpellLevel`, `UserRole`, ...) plus backward-compatible raw string
  lists used by DB check constraints.
