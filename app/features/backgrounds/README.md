# Backgrounds Catalog

Reference catalog of character backgrounds. A background carries base fields
(name, suggestion texts, description), granted skills (`background_skills`
M2M), starting equipment (`source_items` rows pointing at `items`), and its
own BACKGROUND-source features.

## Capabilities / Endpoints

Mounted under `/backgrounds` by `router.py` (one `include_router` per
capability, same `Backgrounds` tag):

| Capability | Endpoints |
| --- | --- |
| `crud/` | `GET ""` (paginated listing), `GET /{background_id}` (full picture), `POST ""` (GM), `PATCH /{background_id}` (GM), `DELETE /{background_id}` (Founder) |
| `skills/` | `PUT /backgrounds/skills?background_id=` — full-replace granted skills (GM) |
| `items/` | `GET /backgrounds/items?background_id=`, `PUT /backgrounds/items?background_id=` — full-replace starting equipment (GM) |
| `features/` | `GET /backgrounds/features?background_id=` — cached per-background feature list (read-only; GM feature create/edit/delete is central: `POST /features`, `PATCH/DELETE /features/{id}`) |

All capability endpoints identify the background via the required
`background_id` query parameter (query-style IDs). Deps live in
`dependencies.py` (`BackgroundCrudDep`, `BackgroundFeaturesDep`,
`BackgroundSkillsDep`, `BackgroundItemsDep`).

## Service Composition & Create Seeding

Each capability service extends `BaseService` and inherits the shared engine:

- `crud/service.py:BackgroundCrudService` extends `CachedService` and composes
  `BackgroundFeatureService` + `BackgroundSkillsService` explicitly in
  `__init__` (no mixin MRO).
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

`create_background` seeds association rows at create time inside one
`_atomic()` transaction: it resolves `granted_skills` through the skills
service (`resolve_skills`) and, when non-empty, attaches them via
`set_skills_for_background(..., commit=False)` next to the new `Background`
row. Features and starting items are deliberately NOT part of create — they
are attached afterwards through their own endpoints.

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

- `BackgroundFullResponse` (returned by `GET /backgrounds/{id}`, cached as a
  single unit) embeds everything: base fields, `granted_skills`,
  `starting_items`, plus its own BACKGROUND-source `features`. The plain
  listing response is light (id/name/granted_skills only); PATCH returns
  `BackgroundResponse` (no features).
- Delete is blocked (409) only once one of the background's features has been
  granted to a character (`is_in_use` check); characters merely referencing
  the background get `background_id` set to NULL.
- Character creation merges background-granted skills into the proficiency
  set server-side (deduplicated with class/race picks); see
  `characters/crud/service.py`.
