# Subraces Catalog (`app/features/subraces/`)

Standalone reference catalog for the `Subrace` entity, mounted at `/subraces`
(the parent race is identified by `race_id`). A subrace belongs to exactly one
race; its features are `Feature` rows with `source_type=SUBRACE`.

The package imports nothing from `app/features/races/`; the schemas and cache helper it shares with races live in `app/features/shared/catalog/`, the feature reader in
`features/crud/source_features.py` and the ability-bonus mixin in `characters/progression/source_bonuses.py`.

## Layout

```
subraces/
├── router.py            # assembles /subraces (one include_router per capability)
├── dependencies.py      # SubraceCrudDep, SubraceFeaturesDep, SubraceAbilityBonusesDep, SubraceTagsDep, SubraceImageDep
├── cache.py             # SUBRACE_CACHE_NAMESPACES, SUBRACE_CRUD_CACHE_NAMESPACES (+spells), SUBRACE_DELETE_NAMESPACES, invalidate_subrace_cache()
├── crud/                # subrace CRUD, race-scoped listing/lookup
├── features/            # read-only cached SUBRACE-source feature list
├── ability_bonuses/     # PUT /ability-bonuses (service built on characters/progression/source_bonuses.py)
├── tags/                # PUT /tags
└── image/               # catalog image upload/delete
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/subraces?race_id=` | open | Light rows (id/race_id/name/image_url) of the race's subraces, ordered by name. Missing race -> 404. |
| POST | `/subraces` | GM | Base fields (`race_id`, `name`, `description`); duplicate name within the race -> 409; missing race -> 404. |
| GET | `/subraces/{subrace_id}` | open | Full `SubraceResponse`: base fields, `ability_bonuses`, `tags`, SUBRACE-source `features`; cached under `races:subrace:get_by_id`. |
| PATCH | `/subraces/{subrace_id}` | GM | `name`/`description`; `race_id` is immutable. Name clash within the same race -> 400, a name used by another race is fine. Explicit `null` -> 422. |
| DELETE | `/subraces/{subrace_id}` | Founder | 409 while a character references the subrace; the stored image is removed. |
| PUT | `/subraces/{subrace_id}/ability-bonuses` | GM | Full replace; duplicates, `bonus` outside -10..10 or more than six entries -> 422. |
| PUT | `/subraces/{subrace_id}/tags` | GM | Full replace; unknown ids -> 400, malformed ids -> 422. |
| GET | `/subraces/{subrace_id}/features` | open | Cached SUBRACE-source feature list. |
| PUT | `/subraces/{subrace_id}/image` | GM | Multipart upload/replace -> `{"image_url"}`. |
| DELETE | `/subraces/{subrace_id}/image` | GM | Clears `image_url` and removes the stored object. |

Input bounds are the ones of the race catalog (`name` 1..100 after trimming, ids positive int32, id lists up to 100).

## Service composition

`SubraceCrudService` extends `BaseService` (only `get_by_id` is cached, with its own key because the default one
would collide with `RaceCrudService.get_by_id` in the shared `races` namespace).

- `get_by_id` makes one load: `SubraceRepository.default_load_options` already eager-loads the SUBRACE-source
  features, so the response is built straight from the ORM row.
- Race existence is checked by `SubraceRepository.race_exists` (a single-column select); there is no race repository.
- Name uniqueness is race-scoped. On create the race comes from the payload; on a rename
  `SubraceRepository._check_uniqueness` scopes by the race of the row being updated (`uq_subrace_race_id_name`).
- `delete` runs the generic in-use guard (`Character.subrace_id`), purges `SUBRACE_DELETE_NAMESPACES` after commit
  and removes the image.
- `SubraceAbilityBonusService`: existence check, write and `reconcile_characters_for_source` in one `_atomic()`.

## Cache invalidation

Subrace reads share the `races` namespace (a race detail embeds `SubraceBrief` rows). Each write purges in one
`invalidate_many` call after commit: `races` (ability bonuses, image), `races` + `spells` (create/update; spell listings embed subrace names), `races` + `tags` (tags),
`races` + `subrace_features` + `features` + `spells` (delete, whose cascade removes the subrace's features). `characters` is
not purged; affected characters are refreshed by the bonus reconcile. Feature writes purge `subrace_features`/`races`
through the central `FeatureCrudService`.
