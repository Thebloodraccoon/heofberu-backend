# Features Catalog (`app/features/features/`)

The **single central feature manager**: every feature in the system — standalone
(FEAT/OTHER) or owned by a class/subclass/race/subrace/background — is created,
read, updated and deleted through this one catalog. It owns the **effect
engine** (choice groups + six typed fixed-effect tables) that replaced the old
`ability_increases` subpackage, and it is the only place the source catalogs
write features from (per-catalog feature writes route here — see the "Feature
writes are centralized" rule).

## Layout

```
features/
├── router.py            # assembles /features (crud + effects)
├── dependencies.py      # FeatureCrudDep, FeatureEffectsDep
├── cache.py             # FEATURE_CACHE_NAMESPACES + invalidate_feature_cache()
├── exceptions.py        # FeatureNotFoundException (404), InvalidFeatureSourceException (400)
├── crud/                # identity schemas, repository, FeatureCrudService, router
└── effects/             # the effect engine: schemas, FeatureEffectsService, router
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/features` | open | Paginated `Page[FeatureGetAllResponse]` of **standalone OTHER** features only (id/name/source_type/FKs/level/`ability_effects`), ordered by name; `search` on name. Source-owned features are listed through their parent record. |
| GET | `/features/{feature_id}` | open | Full `FeatureResponse` for any source, embedding the **whole effect tree** (choice groups + all six fixed-effect lists). |
| POST | `/features` | GM | Create a feature of **any** source type, including `FEAT` (feat rows carry `min_level`/`prerequisite_*`). Source FK + `level` rules enforced at the schema layer (422). |
| PATCH | `/features/{feature_id}` | GM | Editable fields only: `name`, `level`, `description` (+ `min_level`/`prerequisite_*` for FEAT rows). `source_type` and its FK are **immutable** — ownership is permanent. Level-rule violations → 400 (`InvalidFeatureSourceException`). |
| DELETE | `/features/{feature_id}` | GM | Cascades away `CharacterFeature` grants; re-reconciles the owning record's characters. |
| GET/PUT | `/features/{feature_id}/effects` | open / GM | Read / **full-replace** the feature's fixed effects across all six tables (send `[]` to clear); choice groups untouched. |
| GET/PUT | `/features/{feature_id}/choice-groups` | open / GM | Read / **full-replace** the feature's choice-group tree (delete-orphan cascade; stale option effects re-synced on the next grant refresh). |

## The effect engine

A feature's mechanical payload lives in `app/models/features/feature_engine_models.py`
and is served as three things:

- **Six fixed-effect lists** (`FeatureEffectsUpdate`): `ability_effects`,
  `skill_effects`, `saving_throw_effects`, `armor_effects`, `weapon_effects`,
  `spell_effects`. A fixed effect applies automatically to any character
  granted the feature.
- **Choice groups** ("pick N of M", `ChoiceGroupsUpdate`) — each group is
  pinned to one `choice_type` (`SKILL`/`SPELL`/`ABILITY_SCORE`/
  `SAVING_THROW`/`ARMOR`/`WEAPON`); every option in it may only populate the
  one effect-list field that type allows, enforced on write. Groups are
  independent of the fixed effects and are written separately.
- **`FeatureEffectsResponse`** aggregates both (fixed + choice groups) and is
  what `GET /features/{feature_id}` / feats reads serialize.

Payload-item rules (schema-enforced, 422):
- `AbilityEffectItem`: `ability` + `amount`, plus optional `new_cap` — **20–30
  range** (mirrors the legacy ASI validation). Fixed `ability_effects` must not
  repeat an ability.
- `SkillEffectItem`: `skill_id` (`None` = "any skill", choice options only) and
  `grants_expertise`.
- `SavingThrowEffectItem`: `ability`. `ArmorEffectItem`: `armor_type`.
- `WeaponEffectItem`: **exactly one** of `weapon_category` / `item_id`.
- `SpellEffectItem`: a concrete `spell_id` **or** an open filter
  (`spell_school` / `spell_level_max`) — never both.
- A feature may have **at most one** choice group offering ability-score
  effects (`feat_ability_score_effects` and every ASI answer path assumes this).

## FeatureCrudService

`FeatureCrudService` extends `CachedService`; `cache_namespaces =
FEATURE_CACHE_NAMESPACES = ("features",)`. Beyond the standard CRUD it owns:

- **`list_for_source(source_type, source_id)`** — uncached `NestedFeatureResponse`
  listing; the parent catalogs cache their own feature lists under dedicated
  namespaces instead. Raises `ValueError` for FEAT/OTHER (no source FK).
- **`create_feature_for_source` / `create_features_for_source`** — nested
  seeding used by the parent catalogs' create payloads; run inside the caller's
  transaction with `commit=False` and re-validate the merged payload through
  `FeatureCreate`.
- **Character reconciliation** — every source-owned feature create/update/delete
  re-reconciles auto-granted `character_features` in the same transaction via
  `reconcile_characters_for_source` (the known one-way
  `characters.progression.feature_sync` import — never commits, no cycle).
- **`_purge_feature_cache`** — after each write, purges the shared `features`
  namespace PLUS the owning catalog's list namespace
  (`SOURCE_FEATURE_LIST_NAMESPACE`: class_features / subclass_features /
  race_features / subrace_features / background_features) and its parent-read
  namespace (`SOURCE_PARENT_READ_NAMESPACE`: classes / classes / races / races /
  backgrounds). FEAT and OTHER features are standalone and purge only
  `features`.

## The FEAT source type

The old README's claim that FEAT was retired is **no longer true**. Since the
unified-feature migration (`c7c6838`) feats are ordinary `Feature` rows with
`source_type=FEAT`, carrying the `min_level`/`prerequisite_*` columns
(`FeatPrerequisiteFields`, re-used by `app/features/feats/crud/schemas.py`).
They are managed through the dedicated `/feats` catalog — which is a thin
FEAT-scoped view over this service — but the writable surface is identical:
`POST /features` accepts them, and their effects live in the same effect engine
(their ASI alternatives are flattened into the legacy `ability_score_increases`
shape by the feats catalog). FEAT/OTHER rows are never auto-granted to
characters, so they need no reconciliation.

## FeatureEffectsService

`FeatureEffectsService` (in `effects/`, exposed via `FeatureEffectsDep`) owns
the two write endpoints above. Both are **full replaces** executed inside the
request transaction; after flushing the replacement rows they re-materialize
every character currently granted the feature via
`refresh_feature_effect_caches` → `reconcile_effect_rows_for_feature` (one-way
characters import, `autoflush=False`-safe), commit, then invalidate the
`features` cache.

The exception/error split to document: schema-level rule violations (wrong FK,
duplicate ability, out-of-range `new_cap`, two ASI groups) surface as **422**
from Pydantic validators; service-level level-rule violations on PATCH surface
as **400** (`InvalidFeatureSourceException`).