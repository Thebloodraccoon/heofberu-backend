# Subraces Catalog (`app/features/subraces/`)

Standalone reference catalog for the `Subrace` entity, split out of the races
domain and mounted at the top-level `/subraces` prefix (the parent race is
identified by `race_id`). A subrace is owned by exactly one race; its features
are `Feature` rows with `source_type=SUBRACE`.

## Layout

```
subraces/
├── router.py            # assembles /subraces (one include_router per capability)
├── dependencies.py      # SubraceCrudDep, SubraceFeaturesDep, SubraceAbilityBonusesDep, SubraceImageDep
├── cache.py             # SUBRACE_CACHE_NAMESPACES + invalidate_subrace_cache()
├── crud/                # subrace CRUD, race-scoped listing/lookup
├── features/            # read-only cached SUBRACE-source feature list
├── ability_bonuses/     # ability-bonus full replacement (primitives shared with races)
└── image/               # catalog image upload/delete
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/subraces?race_id=` | open | Every subrace of the race as light `SubraceGetAllResponse` rows (id/race_id/name/image_url), ordered by name. Missing race → 404. |
| POST | `/subraces` | GM | Base fields only (`race_id` + `name`/`description`); `ability_bonuses` and `features` are attached afterwards through their own endpoints, `image_url` through `PUT .../image`. Duplicate name within the race → 409. |
| GET | `/subraces/{subrace_id}` | open | Full `SubraceResponse` — base fields + `ability_bonuses` + SUBRACE-source `features`; cached as one unit under the `races` namespace. |
| PATCH | `/subraces/{subrace_id}` | GM | Base fields only (`race_id` is immutable, not in the Update schema); 409 on name clash within the race. |
| DELETE | `/subraces/{subrace_id}` | Founder | Blocked with 409 while any character still references the subrace (`is_in_use` on `Character.subrace_id`). |
| PUT | `/subraces/{subrace_id}/ability-bonuses` | GM | Full replace (empty clears); duplicate abilities → 422. |
| GET | `/subraces/{subrace_id}/features` | open | Cached SUBRACE-source feature list (read-only). |
| PUT | `/subraces/{subrace_id}/image` | GM | Multipart upload/replace (JPEG/PNG/WebP/GIF, max 5 MB) → `{"image_url"}`. |
| DELETE | `/subraces/{subrace_id}/image` | GM | Clears `image_url` and removes the stored object. |

## Service Composition

`SubraceCrudService` extends `BaseService` (not `CachedService` — the listing
is race-scoped and only `get_by_id` is cached, via `@use_cache`) and composes
explicitly in `__init__`:

- `self._features = FeatureCrudService(db)` — `get_by_id` folds the subrace's
  own SUBRACE-source `features` into `SubraceResponse` (cached under
  `races:subrace:get_by_id`). Not used by `create_subrace`, which no longer
  seeds anything nested — features are attached afterwards through the
  `features/` capability endpoint.
- `self._race_repository = RaceRepository(db)` — `list_for_race` / `create`
  `_ensure_race_exists`, translating a missing race into `RecordNotFoundError`
  (404).

Ability bonuses are managed entirely through the separate
`SubraceAbilityBonusService` (`ability_bonuses/`, its own `PUT` endpoint) —
`SubraceCrudService` doesn't compose it; a bonus edit refreshes every
existing character of that subrace's stat cache in the same transaction via
`reconcile_characters_for_source` (the known one-way
`characters.progression.feature_sync` import).

Name uniqueness is **race-scoped** (`SubraceRepository._check_uniqueness`
filters on `race_id`), and deletion runs the generic
`check_in_use_on_delete` guard (`is_in_use` → any `Character` row pointing at
the subrace).

## Cache Invalidation

`cache.py` owns `invalidate_subrace_cache()`, purging `SUBRACE_CACHE_NAMESPACES
= ("races", "subrace_features", "features", "characters")` after every
committed write. `races` is included because `RaceResponse` embeds the subraces
(and their related data) of a race; `characters` because character ability
totals derive from subrace bonuses. `subrace_features` is additionally purged
directly by the central `FeatureCrudService._purge_feature_cache` whenever a
feature write touches a SUBRACE-source feature.