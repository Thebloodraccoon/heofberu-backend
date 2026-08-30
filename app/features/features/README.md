# Features Catalog

Reference catalog for the `Feature` entity — named rules text blocks (name, description, optional `level`) that belong either to a source record (CLASS/SUBCLASS/RACE/SUBRACE/BACKGROUND, pinned via the matching FK) or are standalone (`source_type=OTHER`, GM-granted to any character).

## Layout

- `crud/` — the single central owner of every feature write AND read: `repository.py` (`FeatureRepository`), `service.py` (`FeatureCrudService`), `schemas.py` (central `Feature*` CRUD payloads PLUS the nested feature schemas the parent catalogs embed — the old `features/shared_schemas.py` was folded in), `router.py` (bare router).
- `ability_increases/` — fixed ability-score effects of a feature: `service.py` (`FeatureAbilityIncreaseService`), `schemas.py`, `router.py` (bare router).
- `../features/cache.py` (`FEATURE_CACHE_NAMESPACES`, `invalidate_feature_cache`), `../features/dependencies.py` (`FeatureCrudDep`, `FeatureAbilityIncreasesDep`), `../features/exceptions.py` (404/400 errors), `../features/router.py` — both sub-routers mounted under `/features`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/features` | open | Paginated list of STANDALONE (OTHER) features only; `search` on name. |
| GET | `/features/{feature_id}` | open | A feature of ANY source type. |
| POST | `/features` | GM | Create a feature of ANY source type: pass `source_type` + the matching FK (`class_id`/`subclass_id`/`class_id`/`subrace_id`/`background_id`), or `source_type=OTHER` with no FK. `level` mandatory (1–20) for CLASS/SUBCLASS, optional otherwise. Mismatched FK combo → 422. |
| PATCH | `/features/{feature_id}` | GM | Edit name/level/description of any source type. `source_type` and its FK immutable (422 if sent). A CLASS/SUBCLASS `level` may change within 1–20 but never be cleared (400 otherwise). |
| DELETE | `/features/{feature_id}` | GM | Delete any feature; cascades away `character_features` grants. |
| GET | `/features/ability-increases?feature_id=` | open | A feature's fixed ability-score increases. |
| PUT | `/features/ability-increases?feature_id=` | GM | Full replace of the effect list (empty list clears); duplicate abilities → 422. |

Features are managed centrally through this catalog for EVERY source type. The per-catalog write endpoints (`POST/PATCH/DELETE /races/features`, `/classes/features`, `/backgrounds/features`, `/races/subraces/features`, `/classes/subclasses/features`) were removed — each parent catalog now exposes only a cached GET list (`GET /{source}/features`). The FEAT source type was removed by migration `a9d4f2e8b1c7` and cannot be written (the value survives only inside the Postgres ENUM).

## Service composition

- `FeatureCrudService extends CachedService[...]`. Its `create`/`update_feature`/`delete` accept ANY `source_type` (no standalone guard): the `FeatureCreate` validator pins the source FK and enforces the level rules at parse time; `update_feature` enforces the level rules against the row's existing `source_type`. Module-level helpers: `_get_fk_name` (source type → FK column), `_validate_level_update`, and the `SOURCE_FEATURE_LIST_NAMESPACE` map.
- **Character-grant reconciliation is re-attached to the central writes.** `create`/`update_feature`/`delete` for a source-owned feature (CLASS/SUBCLASS/RACE/SUBRACE/BACKGROUND) call `reconcile_characters_for_source` on the same transaction (`_reconcile_characters` via the known one-way `feature_sync` import) — a new class feature is granted to qualifying characters, a level raise revokes it below the new level, a delete drops its grants and refreshes affected characters' stat caches. OTHER features are never auto-granted, so they skip reconciliation.
- `list_for_source(source_type, source_id)` is UNCACHED by design: each parent catalog caches its own feature LIST (`GET /{source}/features`) under a dedicated namespace (`race_features`, `subrace_features`, `class_features`, `subclass_features`, `background_features`). A central feature write purges the owning catalog's list namespace (only that one) plus the shared `features` namespace via `_purge_feature_cache`.
- `create_feature_for_source` / `create_features_for_source` remain for SEEDING nested `features` inside a parent create payload (run inside the caller's `_atomic()` transaction, `commit=False`; the caller purges its own namespaces).
- `FeatureAbilityIncreaseService extends BaseService[...]` over the same repository and owns only the ability-increase read/replace.

## Ability increases

A feature can own `feature_ability_increases` child rows (ability + amount + optional `new_cap`). They are purely automatic: applied exactly while the feature is granted via `character_features`, counted by the character stats engine; `new_cap` raises an ability's maximum above 20. Replacing them (`set_ability_increases`) refreshes the stat caches of EVERY character currently granted the feature in the same transaction (`refresh_feature_effect_caches` from `characters/progression/feature_sync` — the known one-way import compromise) before committing.

## Cache

`FEATURE_CACHE_NAMESPACES = ("features",)` purged by `invalidate_feature_cache()` after every committed write. In addition, `FeatureCrudService._purge_feature_cache` purges the source-owned feature's catalog list namespace via `SOURCE_FEATURE_LIST_NAMESPACE`, so a write to a class's feature invalidates `class_features` (and only that list). Parent catalogs include `"features"` in their own `cache_namespaces` for their embedded/nested feature reads.