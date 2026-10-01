# Races Catalog (`app/features/races/`)

The `/races` reference catalog: race CRUD plus per-capability subpackages
(features, skills, tags, ability bonuses) and the per-row catalog image.
Subraces live in their own top-level catalog (`app/features/subraces/`,
mounted at `/subraces`).

**Dependency direction.** `races` and `subraces` never import each other. What
both need (ability-bonus schemas, bounded field types, the cache helper) lives in
`app/features/shared/catalog/`; the feature reader is `features/crud/source_features.py` and the
bonus mixin is `characters/progression/source_bonuses.py`; `subraces` imports only from those. `RaceRepository` no longer builds a `SubraceRepository`.

## Layout

```
races/
├── router.py            # assembles /races (one include_router per capability)
├── dependencies.py      # RaceCrudDep, RaceFeaturesDep, RaceSkillsDep, RaceTagsDep, RaceAbilityBonusesDep, RaceImageDep
├── cache.py             # RACE_CACHE_NAMESPACES, RACE_CRUD_CACHE_NAMESPACES (+spells), RACE_DELETE_NAMESPACES, invalidate_race_cache()
├── exceptions.py        # RaceNotFoundException, SubraceNotFoundException (raised by characters)
├── crud/                # race catalog CRUD (CachedService), create is base fields only
├── features/            # read-only cached RACE-source feature list
├── skills/              # granted-skill full replacement (PUT /skills)
├── tags/                # tag full replacement (PUT /tags)
├── ability_bonuses/     # PUT /ability-bonuses (service built on characters/progression/source_bonuses.py)
└── image/               # catalog image upload/delete (ImageStorageService)
```

`app/features/shared/catalog/` contents (shared with subraces):

- `schemas.py`: `AbilityBonusItem`/`AbilityBonusResponse`/`AbilityBonusesUpdate`,
  `SubraceBrief`, `PartialUpdate`, and the bounded types (`CatalogName`, `Description`, `Speed`); the id types
  (`EntityId`, `EntityIdPath`) are in `app/core/types.py` and tag bodies use the shared `TagsUpdate`.
- `cache.py`: `purge_after_commit(db, *namespaces)` (one `invalidate_many` after COMMIT) and `CatalogCacheMixin`,
  which routes `BaseService._invalidate_cache()` through it.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/races` | open | Paginated `Page[RaceGetAllResponse]` (id/name/size/image_url); filters `race_size` (repeatable), `search` on name. |
| GET | `/races/{race_id}` | open | Full `RaceResponse`: base fields, `ability_bonuses`, `granted_skills`, `tags`, RACE-source `features`, `subraces`; cached as one unit. |
| POST | `/races` | GM | Base fields only (`name`, `size`, `speed`, `description`); duplicate `name` -> 400. |
| PATCH | `/races/{race_id}` | GM | Base fields only; duplicate `name` -> 400; explicit `null` -> 422. |
| DELETE | `/races/{race_id}` | Founder | 409 while a character uses the race or one of its subraces. Cascades to subraces and features; stored images are removed. |
| PUT | `/races/{race_id}/ability-bonuses` | GM | Full replace (empty clears); duplicate abilities, `bonus` outside -10..10 or more than six entries -> 422. |
| PUT | `/races/{race_id}/skills` | GM | Full replace (empty clears); unknown ids -> 400, malformed ids -> 422. |
| PUT | `/races/{race_id}/tags` | GM | Full replace (empty clears); unknown ids -> 400, malformed ids -> 422. |
| GET | `/races/{race_id}/features` | open | Cached RACE-source feature list. |
| PUT | `/races/{race_id}/image` | GM | Multipart upload/replace (JPEG/PNG/WebP/GIF, max 5 MB) -> `{"image_url"}`. |
| DELETE | `/races/{race_id}/image` | GM | Clears `image_url` and removes the stored object. |

Input bounds (422 on violation): `name` 1..100 characters after trimming, `speed` 0..200, `description` up to
10 000 characters, id lists up to 100 positive int32 ids, path ids 1..2147483647. `image_url` is not writable
through create/update; it is set only by the image endpoint.

## Service composition

- `RaceCrudService` (`CachedService`): `create_race` writes base fields; `delete` removes the row (the in-use guard
  runs in `RaceRepository.is_in_use`), purges `RACE_DELETE_NAMESPACES`, then deletes the race's and its subraces'
  images (best effort, `storage` is optional so unit tests can build the service without it).
- `RaceRepository.get_subrace(race_id, subrace_id)` is a bare `select(Subrace)`; `characters` calls it to check that
  a subrace belongs to a race.
- `RaceFeatureService` = `SourceFeaturesService` bound to `FeatureSourceType.RACE` (`race_features` namespace).
- `RaceSkillService` = `SkillsManagerMixin`; `RaceTagService` = `TagsManagerMixin`; both are one repository write.
- `RaceAbilityBonusService`: the existence check, the write and `reconcile_characters_for_source` run in one
  `_atomic()`; the cache purge is deferred until COMMIT.

## Cache invalidation

Every write purges only what it can make stale, in one `invalidate_many` call after commit:

| Write | Namespaces |
| ----- | ---------- |
| skills, ability bonuses, image | `races` |
| create/update | `races`, `spells` (spell listings embed race names) |
| tags | `races`, `tags` (tag listings carry `usage_count`) |
| delete | `races`, `race_features`, `subrace_features`, `features`, `spells` (cascade removes features and spell availability) |

`characters` is not purged: character payloads read the race only at creation, and ability-bonus changes refresh
the affected characters inside `reconcile_characters_for_source`. Feature writes purge `race_features`/`races`
through the central `FeatureCrudService`.
