# Races Feature

The `/races` catalog: race CRUD plus per-capability subpackages (features,
skills, ability bonuses) and the self-contained `subraces/` subdomain.

## Layout

```
races/
├── router.py            # assembles /races (one include_router per capability)
├── dependencies.py      # RaceCrudDep, RaceFeaturesDep, RaceSkillsDep, RaceAbilityBonusesDep
├── cache.py             # RACE_CACHE_NAMESPACES + invalidate_race_cache()
├── exceptions.py        # RaceNotFoundException, SubraceNotFoundException
├── schemas.py           # race create/update/response schemas
├── crud/                # race catalog CRUD (CachedService) + create-time seeding
├── features/            # per-race RACE-source feature endpoints
├── skills/              # granted-skill full replacement (PUT /skills)
├── ability_bonuses/     # ability-bonus primitives shared with subraces + PUT /ability-bonuses
└── subraces/            # nested-entity subdomain, mounted at the static /races/subraces prefix
```

## Race CRUD (`crud/`)

`RaceCrudService` extends `CachedService` and composes the other capabilities
explicitly in `__init__` (no mixin MRO): `_skills`, `_ability_bonuses`,
`_nested_features`. Endpoints are the standard set — paginated listing
(`GET /races`), detail read (`GET /races/{id}`), `POST`/`PATCH`/`DELETE`
(GM / GM / Founder).

- The listing is lightweight (`RaceGetAllResponse`: id/name/size only);
  the detail read returns `RaceResponse`, which embeds `ability_bonuses`,
  `granted_skills`, and `subraces` — but NOT `features` (read those via
  `GET /races/features?race_id=...`).
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
| features | `RaceFeatureService` | `SourceFeatureMixin` | pins `_feature_source_type=RACE` |
| skills | `RaceSkillService` | `SkillsManagerMixin` | nothing source-specific beyond the repository |
| ability_bonuses | `RaceAbilityBonusService` | plain `BaseService` | full-replace write |

The mixin engine owns feature CRUD with character-grant reconciliation
(`SourceFeatureMixin`), skill-id resolution and granted-skill replacement
(`SkillsManagerMixin`); the catalog layers pin the source type and purge
cache after commit. All query-style writes identify the race by the required
`race_id` query parameter (`PUT /races/skills?race_id=...`,
`PATCH /races/features?race_id=...&feature_id=...`).

## Subraces subdomain (`subraces/`)

A self-contained capability-oriented subpackage for the second entity a race
owns, mounted by `races/router.py` under a STATIC `/races/subraces` prefix:

- **Parent-scoped query params**: every endpoint takes the owning race as the
  required `race_id` query parameter; mutations additionally take
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
- **`features/`** — `SubraceFeatureService` re-implements `_mutate_feature`
  for its own source type (SUBRACE) because its source lookup goes through
  `_get_or_404_for_race` instead of the shared mixin's plain `_get_or_404`.
- **`ability_bonuses/`** — `SubraceAbilityBonusService`: full-replace write,
  plus the `commit=False` variant used by `create_subrace`.

## Cache invalidation

Two single-point helpers, called by every write AFTER its transaction
commits:

- `races/cache.py:invalidate_race_cache()` — purges
  `("races", "nested_features", "characters")`. `characters` is included
  because character payloads derive `speed` live from the race.
- `subraces/cache.py:invalidate_subrace_cache()` — purges
  `("races", "nested_features")`: subraces (and their features/bonuses) are
  embedded in cached race responses, so any subrace write must invalidate
  the race reads too.

The crud services declare `cache_namespaces = RACE_CACHE_NAMESPACES` /
`SUBRACE_CACHE_NAMESPACES` for their inherited cached reads; capability
services call the invalidation helpers explicitly post-commit.
