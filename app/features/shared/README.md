# Shared reference contexts (`app/features/shared/`)

The cross-catalog building blocks that the capability-oriented catalogs
(backgrounds, races, classes, subclasses/subraces) compose instead of re-implementing.
Three subpackages, each holding ONLY the pieces other catalogs build on:

| Path | Contents |
| --- | --- |
| `features/mixins.py` | `SourceFeatureMixin` — parent-scoped feature CRUD (`list_features` / `add_feature` / `update_feature` / `remove_feature`) with character-grant reconciliation in the same transaction (`_mutate_feature`) |
| `features/nested_service.py` | `NestedFeatureService` — per-source feature list/add/update/remove; reads cached under `nested_features`; writes delegate to `FeatureCrudService` |
| `features/schemas.py` | Shared feature schemas: `NestedFeatureCreate`, `NestedFeatureResponse`, `FeatureUpdate`; plus the consistency helpers `_REQUIRED_FK_BY_SOURCE_TYPE` and `_validate_source_fk_consistency` (used by both the public `features` catalog schemas and the nested flows) |
| `items/mixins.py` | `SourceItemManagerMixin` — starting-equipment `list_items` / `set_items` for a source record |
| `items/nested_service.py` | `NestedSourceItemService` — per-source starting-equipment writes; reads cached under `nested_items`; owns the `source_items` row logic directly |
| `items/schemas.py` | Shared starting-equipment schemas: `SourceItemEntry`, `SourceItemsUpdate`, `SourceItemResponse`, `ItemBriefResponse` |
| `skills/mixins.py` | `SkillsManagerMixin` (granted/available-skill full replace via `_set_skills_method`) and `SkillLookupMixin` (repository skill-id lookup). No skill schemas/services live here — those belong to the `skills` catalog |

## Who composes them

- **Catalogs import only `app.core`, `app.models` and `app.features.shared`** — never
  another catalog. The reverse edge is fine: the shared nested services delegate their
  writes to the public catalogs (`shared/features/nested_service.py` imports
  `FeatureCrudService`, `shared/items/nested_service.py` imports `ItemRepository`).
- Parent services hold one instance each: `self._features = NestedFeatureService(db)` /
  `self._items = NestedSourceItemService(db)`.
- Capability-oriented catalogs split the same mixins across their per-capability services:
  `XFeatureService(SourceFeatureMixin)`, `XItemsService(SourceItemManagerMixin)`,
  `XSkillsService(SkillsManagerMixin)`. The catalog adds only source-type pinning, the
  cache namespaces / post-commit purge, and (where the FullResponse embeds features)
  an extra catalog-namespace purge inside `_mutate_feature`.
- The nested-entity subdomains (`classes/subclasses`, `races/subraces`) host their own
  feature services (`SubclassFeatureService` / `SubraceFeatureService`) that duplicate the
  `_mutate_feature` pattern for their source type, because they resolve the source through
  a class/race-scoped 404 helper rather than the mixin's plain `_get_or_404`.

## Known one-way import compromise

`shared/features/mixins.py` imports
`app.features.characters.progression.feature_sync.reconcile_characters_for_source`
(character-grant reconciliation). That is a shared → characters edge, but `feature_sync`
pulls only `app.models` / `app.constants`, so there is **no import-time cycle**. The same
pattern exists for `features/ability_increases` write paths
(`refresh_feature_effect_caches`). Do not add new reverse dependencies to `feature_sync`.

## Nested cache namespaces

- **`nested_features`** — served by `NestedFeatureService.list_for_source`
  (`GET /{source}/{id}/features`). Invalidation happens AFTER commit, never inside the
  mutating methods: those run with `commit=False` inside the caller's `_atomic()`
  transaction (purging earlier would let a concurrent read repopulate pre-commit rows).
  `SourceFeatureMixin._mutate_feature` calls `self._features.invalidate()` after its
  transaction; catalog-level create/update/delete purge it via the catalog's
  `cache_namespaces` / `invalidate_<catalog>_cache()` helper.
- **`nested_items`** — same pattern for starting equipment
  (`NestedSourceItemService.list_for_source`, `GET /{source}/{id}/items`). Catalogs whose
  responses embed starting items (classes, backgrounds) include it in their invalidation;
  `SourceItemManagerMixin.set_items` purges explicitly after its replace write.

## Behavior contract (do not break)

Per-source feature mutations return the affected `NestedFeatureResponse` built *inside*
the transaction while the row is still loaded — serializing after `commit` would hit
expired attributes (async lazy-load → MissingGreenlet). Removals return `None`. The
reconciliation of affected character grants always runs in the same transaction as the
feature write.
