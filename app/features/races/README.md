# Races Catalog (`app/features/races/`)

The `/races` reference catalog: race CRUD plus per-capability subpackages
(features, skills, ability bonuses) and the per-row catalog image. Subraces
live in their own top-level catalog (`app/features/subraces/`, surfaced under
`/subraces`) — they are NOT a subdomain of this package anymore.

## Layout

```
races/
├── router.py            # assembles /races (one include_router per capability)
├── dependencies.py      # RaceCrudDep, RaceFeaturesDep, RaceSkillsDep, RaceAbilityBonusesDep, RaceImageDep
├── cache.py             # RACE_CACHE_NAMESPACES + invalidate_race_cache()
├── exceptions.py        # RaceNotFoundException, SubraceNotFoundException
├── crud/                # race catalog CRUD (CachedService), create is base fields only
├── features/            # read-only cached RACE-source feature list
├── skills/              # granted-skill full replacement (PUT /skills)
├── ability_bonuses/     # ability-bonus primitives (shared with subraces) + PUT /ability-bonuses
└── image/               # catalog image upload/delete (ImageStorageService)
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/races` | open | Paginated `Page[RaceGetAllResponse]` (id/name/size/image_url); filters `race_size` (repeatable), `search` on name. |
| GET | `/races/{race_id}` | open | Full `RaceResponse` — base fields + `ability_bonuses` + `granted_skills` + RACE-source `features` + `subraces`; eager-loaded off the model relationships, cached as one unit. |
| POST | `/races` | GM | Base fields only (`name`, `size`, `speed`, `description`, `image_url`); duplicate `name` → 409. |
| PATCH | `/races/{race_id}` | GM | Base fields only; duplicate `name` → 409. |
| DELETE | `/races/{race_id}` | Founder | Blocked with 409 while characters still reference the race (`check_in_use_on_delete=True`). |
| PUT | `/races/{race_id}/ability-bonuses` | GM | Full replace of the ability-bonus list (empty clears); duplicate abilities → 422. |
| PUT | `/races/{race_id}/skills` | GM | Full replace of granted skills (empty clears); unknown ids → 400. |
| GET | `/races/{race_id}/features` | open | Cached RACE-source feature list (read-only). |
| PUT | `/races/{race_id}/image` | GM | Multipart upload/replace (JPEG/PNG/WebP/GIF, max 5 MB) → `{"image_url"}`; invalid/oversized → 400. |
| DELETE | `/races/{race_id}/image` | GM | Clears the race's `image_url` and removes the stored object. |

All capability routers identify the owning race by a **path** parameter
(`/{race_id}/...`), consistent with backgrounds/classes — no query-style IDs
remain in this catalog.

## Service Composition & Create Seeding

`RaceCrudService` extends `CachedService` and composes nothing else — it is a
plain catalog CRUD over `RaceRepository` plus the `get_all`/`get_by_id` reads
(eager-loading `Race.ability_bonuses`, `Race.granted_skills`,
`Race.features`, `Race.subraces` through the repository's load options).

- `create_race` writes base fields only (mirrors backgrounds/classes). None of
  `ability_bonuses`/`granted_skills`/`features` are seeded at create — each is
  attached afterwards through its own capability endpoint, or `POST /features`
  (`source_type=RACE`) for features.
- `features/service.py:RaceFeatureService` = read-only cached feature LIST
  (`@use_cache()` under `race_features`), delegating to the central
  `FeatureCrudService.list_for_source` (pinned to `FeatureSourceType.RACE`).
- `skills/service.py:RaceSkillService` = `SkillsManagerMixin` (full-replace
  granted skills, resolved via `SkillLookupMixin` in its repository).
- `ability_bonuses/service.py:RaceAbilityBonusService` = full-replace write;
  a bonus edit also refreshes every existing character of that race's stat
  cache in the same transaction via `reconcile_characters_for_source`
  (the known one-way `characters.progression.feature_sync` import).
- `image/service.py:RaceImageService` = `ImageStorageService` wrapper
  (Supabase Storage, bucket `catalog-images`), composed from `DatabaseDep` +
  `StorageServiceDep` into `RaceImageDep`.

## Cache Invalidation

`cache.py` owns `invalidate_race_cache()`, purging `RACE_CACHE_NAMESPACES =
("races", "race_features", "features", "characters")` after every committed
write. `characters` is included because race features are auto-granted to
characters and character payloads derive `speed` live from the race.
`race_features` is additionally purged directly by the central
`FeatureCrudService._purge_feature_cache` whenever a feature write touches a
RACE-source feature.

## Subraces

Subraces are a **separate catalog** mounted at `/subraces` with `race_id`
scoping — see `app/features/subraces/README.md`. `RaceResponse.subraces`
embeds `SubraceGetAllResponse` rows, so race reads (and the shared `races`
cache namespace) are invalidated by every subrace write too
(`SUBRACE_CACHE_NAMESPACES` includes `"races"`).