# Shared reference contexts (`app/features/shared/`)

The cross-catalog building blocks that the capability-oriented catalogs
(backgrounds, races, classes, subclasses/subraces) compose instead of re-implementing.
Five subpackages (`catalog`, `images`, `items`, `skills`, `tags`), each holding ONLY the pieces other catalogs build on:

| Path | Contents |
| --- | --- |
| `catalog/schemas.py` | Bounded field types (`CatalogName`, `Description`, `Speed`), `PartialUpdate`, ability-bonus schemas, `SubraceBrief` — shared by the race and subrace catalogs. The int32 id types `EntityId` / `EntityIdPath` / `INT32_MAX` live in `app.core.types` |
| `catalog/cache.py` | `purge_after_commit` and `CatalogCacheMixin` (post-commit purge through `invalidate_many`) |
| `images/service.py` | `EntityImageService` — upload/remove one catalog entity's image, persist `image_url`, purge the owning cache |
| `tags/mixins.py`, `tags/schemas.py` | `TagLookupMixin` / `TagsReplaceMixin` / `TagsManagerMixin` (one transaction: check, resolve, write; `_after_tags_set` hook for the post-commit purge) and the shared tag schemas (`TagsUpdate`: ids bounded to int32, at most 100) |
| `items/mixins.py` | `SourceItemManagerMixin` — starting-equipment `list_items` / `set_items` for a source record |
| `items/nested_service.py` | `NestedSourceItemService` — per-source starting-equipment writes; reads cached under `nested_items`; owns the `source_items` row logic directly |
| `items/schemas.py` | Shared starting-equipment schemas: `SourceItemEntry`, `SourceItemsUpdate`, `SourceItemResponse`, `ItemBriefResponse` |
| `skills/mixins.py` | `SkillsManagerMixin` (granted/available-skill full replace in one transaction via `_set_skills_method`) and `SkillLookupMixin` (repository skill-id lookup). No skill schemas/services live here — those belong to the `skills` catalog |

> The former `features/` subpackage was ELIMINATED in the feature-centralization
> refactor: the whole feature engine (any-source `FeatureCrudService.create` /
> `update_feature` / `delete` / `list_for_source`, the nested schemas
> `NestedFeatureCreate` / `NestedFeatureResponse`, `FeatureUpdate`, and the
> consistency helpers `_REQUIRED_FK_BY_SOURCE_TYPE` / `_validate_source_fk_consistency`)
> now lives in the `features` catalog under `crud/`. See `app/features/features/README.md`
> and the Source-Owned Features section of `.rules/architecture.md`.

## Who composes them

- **Dependency direction.** `shared` sits BELOW the catalogs: it imports only `app.core`,
  `app.models`, `app.constants` and, as its single feature edge, the items catalog
  (`shared/items/nested_service.py` uses `ItemRepository` to validate item ids). It never
  imports `features`, `characters` or any other catalog; `tests/unit/test_architecture.py`
  enforces this and also forbids runtime import cycles anywhere in `app/`. Catalogs import
  `app.core`, `app.models`, `app.features.shared` and `app.features.features.crud`
  (the feature engine) - never a sibling catalog (races and subraces do not import each other).
- Code that needs the feature engine or the characters lives with its owner, not here:
  `features/crud/source_features.py` (`SourceFeaturesService`, cached read-only feature list
  of a race/subrace) and `characters/progression/source_bonuses.py`
  (`AbilityBonusesManagerMixin`, race/subrace bonus replacement + character reconciliation).
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

## Catalog -> characters edge

`FeatureCrudService` / `FeatureEffectsService` (create/update/delete, effect edits) and the
race/subrace ability-bonus services call
`app.features.characters.progression.feature_sync` (`reconcile_characters_for_source`,
`refresh_feature_effect_caches`) so a GM edit refreshes every existing character's
`character_ability_scores` row in the same transaction. The packages are mutually dependent
(characters read catalog repositories), but there is **no module-level import cycle**.
Do not add new reverse dependencies to `feature_sync` beyond `characters.*`, `app.models`
and `app.constants`.

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