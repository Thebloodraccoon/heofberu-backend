# Backgrounds Catalog

Reference catalog of character backgrounds. A background carries base fields
(name, description, `starting_gold`), granted skills (`background_skills`
M2M), a suggestion pool (`background_suggestions`, one row per suggested
personality-card entry), starting equipment (`source_items` rows pointing at
`items`), and its own BACKGROUND-source features.

## Capabilities / Endpoints

Mounted under `/backgrounds` by `router.py` (one `include_router` per
capability, same `Backgrounds` tag). Every capability router carries the
`/backgrounds/{background_id}` prefix — `background_id` is a path parameter,
not a query parameter:

| Capability | Endpoints |
| --- | --- |
| `crud/` | `GET ""` (paginated listing), `GET /{background_id}` (full picture), `POST ""` (GM), `PATCH /{background_id}` (GM), `DELETE /{background_id}` (Founder) |
| `skills/` | `PUT /backgrounds/{background_id}/skills` — full-replace granted skills (GM) |
| `items/` | `GET /backgrounds/{background_id}/items`, `PUT /backgrounds/{background_id}/items` — full-replace starting equipment (GM) |
| `features/` | `GET /backgrounds/{background_id}/features` — cached per-background feature list (read-only; GM feature create/edit/delete is central: `POST /features`, `PATCH/DELETE /features/{id}`) |
| `suggestions/` | `GET /backgrounds/{background_id}/suggestions`, `PUT /backgrounds/{background_id}/suggestions` — full-replace the personality-card suggestion pool (GM) |

Deps live in `dependencies.py` (`BackgroundCrudDep`, `BackgroundFeaturesDep`,
`BackgroundSkillsDep`, `BackgroundItemsDep`, `BackgroundSuggestionsDep`).

## Service Composition & Create Seeding

Each capability service extends `BaseService` and inherits the shared engine:

- `crud/service.py:BackgroundCrudService` extends `CachedService` and composes
  `BackgroundFeatureService` explicitly in `__init__` (no mixin MRO) — needed
  by `get_by_id` to fold in `features`.
- `features/service.py:BackgroundFeatureService` = read-only cached feature
  LIST (`@use_cache()` under `background_features`), delegating to the
  central `FeatureCrudService.list_for_source` (pinned to
  `FeatureSourceType.BACKGROUND`).
- `items/service.py:BackgroundItemsService` = `SourceItemManagerMixin`
  delegating to the shared `NestedSourceItemService`. Background starting
  equipment is **fixed** — there are no item choice groups for backgrounds
  (the `choice-groups` mechanic exists for classes only).
- `skills/service.py:BackgroundSkillsService` = `SkillsManagerMixin`
  (+ `SkillLookupMixin` in its repository for skill-id resolution).
- `suggestions/service.py:BackgroundSuggestionsService` = its own small
  list/full-replace service over `BackgroundSuggestionsRepository`
  (`background_suggestions`, delete+insert on write). No `sort_order` — the
  pool is unordered by design, a player picks from the set or rolls one at
  random rather than working off a numbered list.

`create_background` writes base fields only. `granted_skills`, `suggestions`,
`starting_items`, and `features` are all deliberately NOT part of create —
each is attached afterwards through its own capability endpoint, same as
every other catalog domain (race/class) in this codebase.

## Cache Invalidation

`cache.py` owns the single invalidation point
`invalidate_background_cache()`, purging `BACKGROUND_CACHE_NAMESPACES =
("backgrounds", "background_features", "features", "nested_items")`. Every
capability write calls it after commit; the crud service additionally
declares it as `cache_namespaces` (blunt whole-namespace purge). The `features`
entry covers the background's feature list, and `background_features` is
additionally purged directly by the central `FeatureCrudService`'s
`_purge_feature_cache` (via `SOURCE_FEATURE_LIST_NAMESPACE`) whenever any
feature write touches a BACKGROUND-source feature — central writes never touch
the catalog's own invalidator.

## Notable Rules

- `BackgroundResponse` doubles as both the create/update response and the
  `GET /backgrounds/{id}` response: `get_by_id` folds the background's own
  BACKGROUND-source `features` into it (cached as a single unit), while
  `create`/`update` return it with `features` at its empty default — features
  are attached afterwards through their own endpoint. The plain listing
  response (`BackgroundGetAllResponse`) is light (id/name/granted_skills only).
- Delete is blocked (409) only once one of the background's features has been
  granted to a character (`is_in_use` check); characters merely referencing
  the background get `background_id` set to NULL. Its `granted_skills`,
  `starting_items`/`starting_choice_groups`, and `suggestions` rows cascade
  away with it.
- Character creation merges background-granted skills into the proficiency
  set server-side (deduplicated with class/race picks); see
  `characters/crud/service.py`.
