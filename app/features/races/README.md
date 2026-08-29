# Races Feature

The `/races` catalog: race CRUD plus per-capability subpackages (features,
skills, ability bonuses) and the self-contained `../subraces/` subdomain.

## Layout

```
races/
├── router.py            # assembles /races (one include_router per capability)
├── dependencies.py      # RaceCrudDep, RaceFeaturesDep, RaceSkillsDep, RaceAbilityBonusesDep
├── cache.py             # RACE_CACHE_NAMESPACES + invalidate_race_cache()
├── exceptions.py        # RaceNotFoundException, SubraceNotFoundException
├── schemas.py           # race create/update/response schemas
├── crud/                # race catalog CRUD (CachedService) + create-time seeding
├── features/            # read-only cached RACE-source feature list
├── skills/              # granted-skill full replacement (PUT /skills)
├── ability_bonuses/     # ability-bonus primitives shared with subraces + PUT /ability-bonuses
└── subraces/            # nested-entity subdomain, mounted at the static /races/subraces prefix
```

## Race CRUD (`crud/`)

`RaceCrudService` extends `CachedService` and composes the other capabilities
explicitly in `__init__` (no mixin MRO): `_skills`, `_ability_bonuses`,
`_features` (a `FeatureCrudService` for nested-seed + read delegation). Endpoints are the standard set — paginated listing
(`GET /races`), detail read (`GET /races/{id}`), `POST`/`PATCH`/`DELETE`
(GM / GM / Founder).

- The listing is lightweight (`RaceGetAllResponse`: id/name/size only);
  the detail read returns `RaceResponse`, which embeds `ability_bonuses`,
  `granted_skills`, the race's RACE-source `features`, and `subraces` (the
  dedicated `GET /races/features?race_id=...` list stays available too).
- `create_race` seeds optional `ability_bonuses`, `granted_skills`, and
  nested `features` in one `_atomic()` transaction through the capability
  services (each inner write passes `commit=False`).
- Deletion is blocked while characters still reference the race
  (`check_in_use_on_delete=True` + `RaceRepository.is_in_use`) → 409.

## Per-capability services composing shared mixins

Each capability is a mini-feature (`router.py`/`service.py`[/`repository.py`])
that inherits the shared engine from `app/features/shared/` and adds only the
source-specific bits:

| Capability | Service | Composes | Adds |
|---|---|---|---|
| features | `RaceFeatureService` | `FeatureCrudService` (delegation) | `@use_cache()` list under `race_features`, pinned `_feature_source_type=RACE` |
| skills | `RaceSkillService` | `SkillsManagerMixin` | nothing source-specific beyond the repository |
| ability_bonuses | `RaceAbilityBonusService` | plain `BaseService` | full-replace write + refreshes every affected character's stat cache via `reconcile_characters_for_source` |

The feature engine (any-source create/update/delete + character-grant
reconciliation) is centralized in `app/features/features/crud/service.py`;
each catalog keeps only a cached read LIST. `SkillsManagerMixin` covers
skill-id resolution and granted-skill replacement. All query-style writes
identify the race by the required `class_id` query parameter
(`PUT /races/skills?race_id=...`); feature writes go through the central
`POST /features` / `PATCH`/`DELETE /features/{id}` with
`source_type=RACE&race_id=...` in the body.

## Subraces subdomain (`../subraces/`)

A self-contained capability-oriented subpackage for the second entity a race
owns, mounted by `races/router.py` under a STATIC `/races/subraces` prefix:

- **Parent-scoped query params**: every endpoint takes the owning race as the
  required `class_id` query parameter; mutations additionally take
  `subrace_id=`. Only the DETAIL READ keeps the child in the path —
  `GET /races/subraces/{subrace_id}?race_id=...` — so it cannot collide with
  the listing (`GET /races/subraces?race_id=...`).
- **`base.py`** — `SubraceScopedMixin._get_or_404_for_race`: translates the
  generic `RecordNotFoundError` into the parent-scoped
  `SubraceNotFoundException` (defined in the parent's `exceptions.py`; the
  subdomain has none of its own), also when the row exists but belongs to a
  different race.
- **`crud/`** — `SubraceCrudService`: listing, race-scoped detail read
  (`SubraceFullResponse` = base fields + ability bonuses + SUBRACE-source
  features, cached under `races`), atomic create seeding bonuses + nested
  features, PATCH, DELETE (Founder; characters keep their rows but lose
  `subrace_id`). A missing parent race 404s on create/list via
  `_ensure_race_exists`.
- **`features/`** — `SubraceFeatureService`: read-only cached list
  (`@use_cache()` under `subrace_features`), resolving the source through
  `_get_or_404_for_race` and delegating to the central
  `FeatureCrudService.list_for_source`.
- **`ability_bonuses/`** — `SubraceAbilityBonusService`: full-replace write,
  plus the `commit=False` variant used by `create_subrace`. A bonus edit
  also refreshes every character of that subrace's stat cache via
  `reconcile_characters_for_source` (same one-way import compromise as the
  race ability-bonus write).

## Cache invalidation

Two single-point helpers, called by every write AFTER its transaction
commits:

- `races/cache.py:invalidate_race_cache()` — purges
  `("races", "race_features", "features", "characters")`. `characters` is
  included because race features are auto-granted to characters and
  character payloads derive `speed` live from the race.
- `../subraces/cache.py:invalidate_subrace_cache()` — purges
  `("races", "subrace_features", "features", "characters")`: subraces (and
  their features) are embedded in cached race responses, so any subrace
  write must invalidate the race reads too; `characters` is included
  because ability-score totals in character payloads derive from subrace
  bonuses (mirroring the race namespace).

The crud services declare `cache_namespaces = RACE_CACHE_NAMESPACES` /
`SUBRACE_CACHE_NAMESPACES` for their inherited cached reads; capability
services call the invalidation helpers explicitly post-commit. The
sub-race feature list namespace (`race_features`/`subrace_features`) is
also purged directly by the central `FeatureCrudService._purge_feature_cache`
whenever a feature write touches that source.
