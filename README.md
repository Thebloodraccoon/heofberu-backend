# Heofberu Backend

REST API backend for the **Heofberu** TTRPG companion app — a D&D 5e-style
reference catalog (races, classes, spells, feats, items, ...) plus full
character management with a Game Master panel.

Built with **FastAPI**, **SQLAlchemy 2.0** (async), **PostgreSQL**, **Redis**
and **Alembic**. Python 3.10+, managed with Poetry.

## Quick Start

```bash
# local services (Postgres + Redis)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# apply migrations, then run the API
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

Interactive docs are served at `/docs` (disabled in production).

## Architecture

Strict layering: `endpoint → service → repository → model`.
Every application error is an `AppError` subclass mapped to a standardized
error envelope by a single global handler; routers stay thin and never raise.

```
app/
├── core/           # reusable building blocks (see app/core/README.md)
│   ├── base/       #   BaseService / BaseRepository / CachedService / NestedService
│   ├── cache/      #   pooled redis client + @cached decorator + invalidation
│   ├── handlers/   #   global exception handlers (AppError first)
│   ├── security/   #   bcrypt passwords, token verify/blacklist
│   ├── db.py       #   engine/session dependency
│   └── exceptions.py  # AppError regime + data-layer exceptions
├── features/       # one folder per domain — each has its own README.md
│   ├── auth/ users/ admin/ ping/          # flat features
│   ├── races/ classes/ backgrounds/ feats/# reference catalogs,
│   ├── spells/ features/ items/ skills/   #   capability-oriented
│   ├── shared/     # cross-catalog mixins/services other catalogs compose
│   └── characters/ # compound domain: CRUD, sub-resources, GM panel
├── models/         # SQLAlchemy ORM models, one file per domain
├── settings/       # staged config + pooled settings.get_redis() client
├── middleware/     # request-id, logging, timing, rate limit, error handlers
├── router.py       # mounts every feature router
└── main.py         # app assembly, middleware order, lifespan
```

### Key conventions

- **Reference catalogs** (`races`, `classes`, `backgrounds`, `feats`, `spells`,
  `items`, `features`, `skills`) are split into per-capability mini-features
  (`crud/` + association capabilities such as `features/`, `skills/`,
  `ability_bonuses/`); each catalog's `crud` service composes the others for
  create-time seeding and full responses.
- **Dependency rule**: a catalog imports only `app/core`, `app/models` and
  `app/features/shared` — never another catalog. Shared mixins
  (`SourceFeatureMixin`, `SourceItemManagerMixin`, `SkillsManagerMixin`)
  implement cross-catalog logic once, reconciling character grants on source
  edits within the same transaction.
- **Nested subdomains** (`classes/subclasses`, `races/subraces`,
  `characters/gm_panel`) use parent-scoped query parameters
  (`race_id=`, `character_id=`) on list/write endpoints.
- **Caching**: read-heavy catalog/nested reads go through the Redis-backed
  `@cached` decorator with per-catalog namespaces; every write purges its
  namespaces after commit via `<catalog>/cache.py`.
- **Characters**: creation is a one-shot level-1 contract (server-derived HP,
  mandatory origin feat, merged/deduplicated skills); ability scores are never
  recomputed on reads — writes refresh the `character_ability_scores` cache;
  ASI points live as audited choice rows, keeping base columns pristine.
- Multi-table writes wrap in `_atomic()`; PATCH uses
  `exclude_unset=True`; endpoints document bodies via OpenAPI examples and
  declare exactly the error codes their service raises.

## Testing

Tests are marked `unit` (fast, no DB) and `integration`
(needs the Docker services `heof-test-db` and `heof-test-redis`):

```bash
poetry run pytest tests/unit -q

docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d heof-test-db heof-test-redis
poetry run pytest tests/integration -q
```

Linting/formatting: `poetry run ruff check app tests` /
`poetry run ruff format app tests` (line length 120, double quotes).

## Documentation Map

Every module carries an English `README.md` describing what happens inside:

| Area | README |
|---|---|
| Core building blocks | [`app/core/README.md`](app/core/README.md) |
| Auth | [`app/features/auth/README.md`](app/features/auth/README.md) |
| Users & auth dependencies | [`app/features/users/README.md`](app/features/users/README.md) |
| Admin | [`app/features/admin/README.md`](app/features/admin/README.md) |
| Health check | [`app/features/ping/README.md`](app/features/ping/README.md) |
| Races (+subraces) | [`app/features/races/README.md`](app/features/races/README.md) |
| Classes (+subclasses) | [`app/features/classes/README.md`](app/features/classes/README.md) |
| Backgrounds | [`app/features/backgrounds/README.md`](app/features/backgrounds/README.md) |
| Feats | [`app/features/feats/README.md`](app/features/feats/README.md) |
| Spells | [`app/features/spells/README.md`](app/features/spells/README.md) |
| Features | [`app/features/features/README.md`](app/features/features/README.md) |
| Items | [`app/features/items/README.md`](app/features/items/README.md) |
| Skills | [`app/features/skills/README.md`](app/features/skills/README.md) |
| Shared mixins/services | [`app/features/shared/README.md`](app/features/shared/README.md) |
| Characters (overview) | [`app/features/characters/README.md`](app/features/characters/README.md) |
| Characters: attacks / conditions / spells / progression | `app/features/characters/{attacks,conditions,spells,progression}/README.md` |
| Character GM panel | [`app/features/characters/gm_panel/README.md`](app/features/characters/gm_panel/README.md) |
| ORM models & bootstrap files | [`app/models/README.md`](app/models/README.md) |
| Settings & config stages | [`app/settings/README.md`](app/settings/README.md) |
| Middleware chain | [`app/middleware/README.md`](app/middleware/README.md) |

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.
