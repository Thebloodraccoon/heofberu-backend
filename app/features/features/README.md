# Features Catalog

Reference catalog for the `Feature` entity — named rules text blocks (name, description, optional `level`) that belong either to a source record (CLASS/SUBCLASS/RACE/SUBRACE/BACKGROUND, pinned via the matching FK) or are standalone (`source_type=OTHER`, GM-granted to any character).

## Layout

- `crud/` — standalone CRUD plus the per-source feature management reused by parent catalogs: `repository.py` (`FeatureRepository`), `service.py` (`FeatureCrudService`), `schemas.py`, `router.py` (bare router).
- `ability_increases/` — fixed ability-score effects of a feature: `service.py` (`FeatureAbilityIncreaseService`), `schemas.py`, `router.py` (bare router).
- `../features/cache.py`, `../features/dependencies.py` (`FeatureCrudDep`, `FeatureAbilityIncreasesDep`), `../features/exceptions.py` (404/400 errors), `../features/router.py` — both sub-routers mounted under `/features`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/features` | open | Paginated list of STANDALONE (OTHER) features only; `search` on name. |
| GET | `/features/{feature_id}` | open | Standalone features only — a source-owned feature 404s here. |
| POST | `/features` | GM | `StandaloneFeatureCreate`: `source_type` pinned to OTHER; no source FK may be set. |
| PATCH | `/features/{feature_id}` | GM | Standalone only; `source_type` and its FK immutable, only name/level/description editable. |
| DELETE | `/features/{feature_id}` | GM | Standalone only; cascades away `character_features` grants. |
| GET | `/features/ability-increases?feature_id=` | open | A feature's fixed ability-score increases. |
| PUT | `/features/ability-increases?feature_id=` | GM | Full replace of the effect list (empty list clears); duplicate abilities → 422. |

Source-owned features (class/subclass/race/subrace/background) are NOT managed here directly by clients — they live under their parent's per-feature endpoints, which delegate to `FeatureCrudService.create_feature_for_source` / `update_feature_for_source` / `delete_feature_for_source` / `create_features_for_source` (nested create payloads). The FEAT source type was removed by migration `a9d4f2e8b1c7` and cannot be written (the value survives only inside the Postgres ENUM).

## Service composition

- `FeatureCrudService` extends `CachedService[...]`. Its module-level helpers `_get_fk_name` (source type → FK column via the shared `_REQUIRED_FK_BY_SOURCE_TYPE`) and `_get_source_feature` (fetch + ownership check → 404/400) back the per-source methods used by every parent catalog. Standalone reads/writes guard with `_require_standalone` so `/features/` never touches a source-owned row.
- `FeatureAbilityIncreaseService` extends `BaseService[...]` over the same repository and owns only the ability-increase read/replace.

## Ability increases

A feature can own `feature_ability_increases` child rows (ability + amount + optional `new_cap`). They are purely automatic: applied exactly while the feature is granted via `character_features`, counted by the character stats engine; `new_cap` raises an ability's maximum above 20. Replacing them (`set_ability_increases`) refreshes the stat caches of EVERY character currently granted the feature in the same transaction (`refresh_feature_effect_caches` from `characters/progression/feature_sync` — the known one-way import compromise) before committing.

## Cache

`FEATURE_CACHE_NAMESPACES = ("features",)` purged by `invalidate_feature_cache()` after every committed write. Parent catalogs include `"features"` in their own `cache_namespaces` for their embedded/nested feature reads.
