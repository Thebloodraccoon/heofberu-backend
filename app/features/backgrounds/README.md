# Backgrounds Catalog

Reference catalog of character backgrounds. A background carries base fields
(name, description, `starting_gold`), granted skills (`background_skills`
M2M), tags, a suggestion pool (`background_suggestions`, one row per suggested
personality-card entry), starting equipment (`source_items` rows plus
"pick N of M" choice groups pointing at `items`), and its own
BACKGROUND-source features.

## Capabilities / Endpoints

Mounted under `/backgrounds` by `router.py` (one `include_router` per
capability, same `Backgrounds` tag). Every capability router carries the
`/backgrounds/{background_id}` prefix — `background_id` is a path parameter,
not a query parameter:

| Capability | Endpoints |
| --- | --- |
| `crud/` | `GET ""` (paginated listing, id/name), `GET /{background_id}` (full picture), `POST ""` (GM), `PATCH /{background_id}` (GM), `DELETE /{background_id}` (Founder) |
| `skills/` | `PUT /backgrounds/{background_id}/skills` — full-replace granted skills (GM) |
| `tags/` | `PUT /backgrounds/{background_id}/tags` — full-replace tags (GM) |
| `items/` | `GET/PUT /backgrounds/{background_id}/items` — starting equipment; `GET/PUT /backgrounds/{background_id}/choice-groups` — "pick N of M" equipment alternatives (PUT is GM, full replace) |
| `features/` | `GET /backgrounds/{background_id}/features` — cached per-background feature list (read-only; feature create/edit/delete is central: `POST /features`, `PATCH/DELETE /features/{id}`) |
| `suggestions/` | `GET/POST /backgrounds/{background_id}/suggestions`, `PATCH/DELETE /backgrounds/{background_id}/suggestions/{suggestion_id}` — the personality-card suggestion pool (writes GM) |

Deps live in `dependencies.py` (`BackgroundCrudDep`, `BackgroundFeaturesDep`,
`BackgroundSkillsDep`, `BackgroundItemsDep`, `BackgroundSuggestionsDep`,
`BackgroundTagsDep`).

## Service Composition

- `crud/service.py:BackgroundCrudService` extends `CachedService`. Its
  `get_by_id` is ONE eager-loaded read (skills, items, choice groups,
  suggestions, tags and the BACKGROUND-source `features` with their effect
  tree) serialized into `BackgroundResponse`, cached as a single unit.
  `create_background` seeds one placeholder suggestion (`text="-"`) per
  `BackgroundSuggestionType` in the same transaction; skills, tags, items and
  features are attached afterwards through their own endpoints. `delete` reads
  the bare row (no effect tree).
- Every other capability service extends `capability.py:BackgroundCapabilityService`
  (a thin `BaseService` binding the shared `BackgroundResponse`), so each
  endpoint answers with the full background:
  - `features/service.py:BackgroundFeatureService` — read-only cached list
    (`background_features`), delegating to `FeatureCrudService.list_for_source`.
  - `items/service.py:BackgroundItemsService` — `SourceItemManagerMixin` +
    `ChoiceGroupManagerMixin` over the shared `NestedSourceItemService`.
  - `skills/service.py:BackgroundSkillsService` — `SkillsManagerMixin`.
  - `tags/service.py:BackgroundTagService` — `TagsManagerMixin`.
  - `suggestions/service.py:BackgroundSuggestionsService` — per-suggestion CRUD.
    Character creation needs exactly one suggestion per type, so the last
    suggestion of a type can be neither deleted nor re-typed (409,
    `LastSuggestionOfTypeError`); the background row is locked
    (`SELECT ... FOR UPDATE`) so two concurrent requests can't both pass.

## Cache Invalidation

`cache.py` owns the namespace tuples; every write purges after commit
(`BaseService._invalidate_cache` inside `_atomic()` defers it; outside it the
repository has already committed):

- `BACKGROUND_CACHE_NAMESPACES = ("backgrounds",)` — base fields, skills, tags,
  suggestions, create.
- `BACKGROUND_ITEMS_CACHE_NAMESPACES` — adds `nested_items` (items and choice groups).
- `BACKGROUND_DELETE_CACHE_NAMESPACES` — adds `background_features` and
  `features` (the delete cascades to the background's features).

Background features written through `/features` purge `background_features`
and `backgrounds` themselves (`invalidate_feature_cache_after_commit`). Skill/item
catalog edits purge `backgrounds` from their side.

## Notable Rules

- `BackgroundResponse` is the response of `GET /{id}`, `PATCH`, and every
  capability `PUT`. All of them come from the same eager load, so `features`
  is always populated and identical to `GET /{id}/features`.
- Delete is blocked (409) once any of the background's features is granted to a
  character (one `EXISTS` query, however many grants exist). The feature rows
  are locked first, because `character_features.feature_id` cascades and a grant
  slipping in between the guard and the DELETE would otherwise be wiped
  silently. Characters merely referencing the background get `background_id`
  set to NULL by the database (`passive_deletes` on `Background.characters`);
  skills, tags, items, choice groups, suggestions and features cascade away.
- Input bounds: `name` 1..100 (whitespace-trimmed), `starting_gold` 0..1e9, PATCH
  rejects an explicit `null` for any field (422), `skill_ids` unique ints.
  Duplicate names answer 400 (`RecordAlreadyExistsError`, platform-wide).
- Character creation merges background-granted skills into the proficiency
  set server-side (deduplicated with class/race picks) and reads the
  background's choice groups like a class's; see `characters/crud/service.py`.
