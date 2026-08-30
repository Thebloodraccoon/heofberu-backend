# Shared reference contexts (`app/features/shared/`)

The cross-catalog building blocks that the capability-oriented catalogs
(backgrounds, races, classes, subclasses/subraces) compose instead of re-implementing.
Two subpackages, each holding ONLY the pieces other catalogs build on:

| Path | Contents |
| --- | --- |
| `items/mixins.py` | `SourceItemManagerMixin` — starting-equipment `list_items` / `set_items` for a source record |
| `items/nested_service.py` | `NestedSourceItemService` — per-source starting-equipment writes; reads cached under `nested_items`; owns the `source_items` row logic directly |
| `items/schemas.py` | Shared starting-equipment schemas: `SourceItemEntry`, `SourceItemsUpdate`, `SourceItemResponse`, `ItemBriefResponse` |
| `skills/mixins.py` | `SkillsManagerMixin` (granted/available-skill full replace via `_set_skills_method`) and `SkillLookupMixin` (repository skill-id lookup). No skill schemas/services live here — those belong to the `skills` catalog |

> The former `features/` subpackage was ELIMINATED in the feature-centralization
> refactor: the whole feature engine (any-source `FeatureCrudService.create` /
> `update_feature` / `delete` / `list_for_source`, the nested schemas
> `NestedFeatureCreate` / `NestedFeatureResponse`, `FeatureUpdate`, and the
> consistency helpers `_REQUIRED_FK_BY_SOURCE_TYPE` / `_validate_source_fk_consistency`)
> now lives in the `features` catalog under `crud/`. See `app/features/features/README.md`
> and the Source-Owned Features section of `.opencode/rules/architecture.md`.

## Who composes them

- **Catalogs import only `app.core`, `app.models`, `app.features.shared` and — the one
  documented feature-catalog edge — `app.features.features.crud.{schemas,service}`** —
  never another catalog. The reverse edges are fine: the shared item writes delegate to
  the items catalog (`shared/items/nested_service.py` imports `ItemRepository`), and no
  shared module imports the features catalog — the features branch is owned wholesale by
  the `features` catalog itself.
- Parent services hold one instance each: `self._features = FeatureCrudService(db)`
  (wrapped in a catalog `XFeatureService` for the cached GET list) /
  `self._items = NestedSourceItemService(db)`.
- Capability-oriented catalogs split the mixins across their per-capability services:
  `XFeatureService` (read-only cached LIST delegating to `FeatureCrudService.list_for_source`),
  `XItemsService(SourceItemManagerMixin)`,
  `XSkillsService(SkillsManagerMixin)`.
- The nested-entity subdomains (`classes/subclasses`, `races/subraces`) host their own
  GET-only feature list services (`SubclassFeatureService` / `SubraceFeatureService`)
  that delegate to `FeatureCrudService.list_for_source` and resolve the source through a
  class/race-scoped 404 helper.

## Known one-way import compromise

`FeaturesCrudService` (create/update/delete) and `features/ability_increases`
(`refresh_feature_effect_caches`) import
`app.features.characters.progression.feature_sync.reconcile_characters_for_source`
(character-grant reconciliation). The race and subrace **ability-bonus**
services reuse that same helper so a GM editing bonuses refreshes every
existing character's `character_ability_scores` cache row in the same
transaction. That is a features/races/subraces → characters edge, but
`feature_sync` pulls only `app.models` / `app.constants`, so there is
**no import-time cycle**. Do not add new reverse dependencies to
`feature_sync`.

## Nested cache namespaces

- **`nested_items`** — starting equipment (`NestedSourceItemService.list_for_source`,
  `GET /{source}/{id}/items`). Catalogs whose responses embed starting items (classes,
  backgrounds) include it in their invalidation; `SourceItemManagerMixin.set_items`
  purges explicitly after its replace write. Invalidation happens AFTER commit, never
  inside the mutating methods: those run with `commit=False` inside the caller's
  `_atomic()` transaction (purging earlier would let a concurrent read repopulate
  pre-commit rows).
- **Feature lists are no longer a nested namespace**: each catalog caches its own
  feature LIST under `race_features` / `subrace_features` / `class_features` /
  `subclass_features` / `background_features`, purged by
  `FeatureCrudService._purge_feature_cache` via `SOURCE_FEATURE_LIST_NAMESPACE`.

## Behavior contract (do not break)

Per-source item mutations return the affected response built *inside* the transaction
while the row is still loaded — serializing after `commit` would hit expired attributes
(async lazy-load → MissingGreenlet). Removals return `None`. Feature writes and their
character-grant reconciliation live in the `features` catalog; do not re-add feature
writes to `shared/`.