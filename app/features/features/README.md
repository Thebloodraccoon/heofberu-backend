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
├── cache.py             # namespace matrix + invalidate_feature_cache_after_commit()
├── exceptions.py        # FeatureNotFoundException (404), InvalidFeatureSourceException (400)
├── crud/                # identity schemas, FeatureRepository (+ feature_summary_loads), FeatureCrudService, router
└── effects/             # the effect engine: schemas, rendering, FeatureEffectsRepository/Service, router
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/features` | open | Paginated `Page[FeatureGetAllResponse]` of **standalone OTHER** features only (id/name/source_type/FKs/level/`has_static_effects`/`has_choices`), ordered by name; `search` on name. Source-owned features are listed through their parent record. |
| GET | `/features/{feature_id}` | open | Full `FeatureResponse` for any source, embedding the **whole effect tree** (`choice_groups` + `static_groups`, the discriminated union of fixed effects — see below). |
| POST | `/features` | GM | Create a feature of **any** source type, including `FEAT` (feat rows carry `min_level`/`prerequisite_*`). Source FK + `level` rules enforced at the schema layer (422). |
| PATCH | `/features/{feature_id}` | GM | Editable fields only: `name`, `level`, `description` (+ `min_level`/`prerequisite_*` for FEAT rows). `source_type` and its FK are **immutable** — ownership is permanent. Rule violations (level outside 1-20, a cleared CLASS/SUBCLASS level, FEAT-only columns on a non-FEAT feature, half a prerequisite) -> 400 (`InvalidFeatureSourceException`). Characters are re-reconciled **only when `level` changes**. |
| DELETE | `/features/{feature_id}` | GM | One transaction. A standalone FEAT/OTHER feature held by a character -> **409** (same guard as `DELETE /feats/{id}`). A source-owned feature cascades its grants away and re-reconciles the owning record's characters before the commit. |
| GET/PUT | `/features/{feature_id}/effects` | open / GM | Read / **diff-update** the fixed effects by row id. Only the effect types **present** in the body are touched (`[]` clears a type); omitted types are left alone. Choice groups untouched. |
| GET/PUT | `/features/{feature_id}/choice-groups` | open / GM | Read / **diff-update** the choice-group tree by id (groups -> options -> effects); `choice_groups` is required. Dropping an option/group a character has already picked clears that pick (reverts to pending) instead of failing. |

## The effect engine

A feature's mechanical payload lives in `app/models/features/feature_engine_models.py`
and is served as three things:

- **Six fixed-effect lists on write** (`FeatureEffectsUpdate`): `ability_effects`,
  `skill_effects`, `saving_throw_effects`, `armor_effects`, `weapon_effects`,
  `spell_effects`. A fixed effect applies automatically to any character
  granted the feature. `PUT /features/{feature_id}/effects` still takes this
  flat six-list shape.
- **Choice groups** ("pick N of M", `ChoiceGroupsUpdate`) — each group is
  pinned to one `choice_type` (`SKILL`/`SPELL`/`ABILITY_SCORE`/
  `SAVING_THROW`/`ARMOR`/`WEAPON`); every option in it may only populate the
  one effect-list field that type allows, enforced on write. Groups are
  independent of the fixed effects and are written separately.
- **`static_groups: list[StaticEffectGroup]` on read** — the six flat lists
  are no longer serialized separately on responses. Instead `Feature.static_groups`
  (a model `@property`, `app/models/features/feature_model.py`) emits one entry
  per **non-empty** fixed-effect relationship, each a discriminated union member
  keyed by `effect_type` (`"ability"` / `"skill"` / `"saving_throw"` / `"armor"`
  / `"weapon"` / `"spell"`) carrying that type's `items` list. `FeatureResponse`,
  `NestedFeatureResponse` and `FeatureEffectsResponse` all expose
  `static_groups` this way, plus `has_static_effects` / `has_choices`
  (denormalized `Feature` columns, maintained by every effect/choice-group
  write — see `FeatureEffectsRepository.refresh_effect_flags`) and a rendered
  `effects_summary` HTML string (a `Feature` `@property`; every interpolated catalog name is HTML-escaped; amounts are signed `+1`/`-1`; option saving throws are in the genitive).
- **`FeatureEffectsResponse`** aggregates `choice_groups` + `static_groups` and
  is what `GET /features/{feature_id}/effects` returns (`GET /features/{feature_id}`
  embeds the same shape inline via `FeatureResponse`).

Payload rules (schema-enforced, 422 — the schemas reject unknown keys):
- `AbilityEffectItem`: `ability` + `amount` (-30..30), optional `new_cap` (**20-30**).
- `SkillEffectItem`: a concrete `skill_id`; `grants_expertise`. `SavingThrowEffectItem`:
  `ability`. `ArmorEffectItem`: `armor_type`. `WeaponEffectItem`: **exactly one** of
  `weapon_category` / `item_id`. `SpellEffectItem`: a concrete `spell_id`.
- A **fixed** skill/spell effect needs its `skill_id`/`spell_id`; an open ("any") option is
  not authorable on a SKILL/SPELL choice group either (`validate_no_open_picks`). Legacy rows
  may still read back with `None`.
- No repeated row `id`, and no repeated effect (same ability / skill / armor type / item /
  category / spell) inside one list — fixed lists and every option alike.
- Bounds: ids 1..2^31-1, `pick_count` 1..50, `sort_order` 0..10 000, <= 50 effects per list,
  <= 50 options per group, <= 20 groups. A feature may have **at most one** `ABILITY_SCORE`
  choice group (`feat_ability_score_effects` assumes it). The `skill_id`/`item_id`/`spell_id` of
  every effect must exist (checked up front, 422 listing the unknown ids).
- Groups accept (and drop) a legacy `label`; every other unknown key is a 422.

Feature identity rules (`FeatureCreate` and `PATCH` alike): `level` 1..20 for every source type
(required for CLASS/SUBCLASS, not allowed for FEAT); `min_level`/`prerequisite_*` only on FEAT
rows; `prerequisite_ability` and `prerequisite_minimum_score` (1..30) are set together;
`name` <= 200 chars.

## FeatureCrudService

`FeatureCrudService` extends `CachedService`; `cache_namespaces =
FEATURE_CACHE_NAMESPACES = ("features",)`. Every write is **one transaction**
(`_atomic()`): the row change, the character reconciliation and — registered with
`invalidate_after_commit` — the cache purge, which runs only after the COMMIT and is dropped on
rollback. Beyond the standard CRUD it owns:

- **`list_for_source(source_type, source_id)`** — uncached `NestedFeatureResponse`
  listing; the parent catalogs cache their own feature lists under dedicated
  namespaces instead. Raises `ValueError` for FEAT/OTHER (no source FK).
- **Character reconciliation** — a source-owned feature create/delete and a `level` change
  re-reconcile auto-granted `character_features` via `reconcile_characters_for_source` (the
  known one-way `characters.progression.feature_sync` import — never commits, no cycle). Any
  other edit only purges the cached payloads of the characters holding the feature.
- **Cache matrix** (`cache.py::feature_namespaces`) — the shared `features` namespace PLUS the
  owning catalog's list namespace (`class_features` / `subclass_features` / `race_features` /
  `subrace_features` / `background_features`) and parent-read namespace (`classes` / `classes` /
  `races` / `races` / `backgrounds` / `feats`). OTHER features purge only `features`.
- **Query budget** — `create` makes no tree queries (a new feature's collections are marked
  loaded-and-empty); `update` loads the tree once and serializes that same object; `delete` loads
  only the bare row. `feature_summary_loads(base, with_names=...)` is the shared eager-load set the
  parent catalogs chain onto; the effect endpoints use `with_names=False`.

## The FEAT source type

The old README's claim that FEAT was retired is **no longer true**. Since the
unified-feature migration (`c7c6838`) feats are ordinary `Feature` rows with
`source_type=FEAT`, carrying the `min_level`/`prerequisite_*` columns
(`FeatPrerequisiteFields`, re-used by `app/features/feats/crud/schemas.py`).
They are managed through the dedicated `/feats` catalog — which is a thin
FEAT-scoped view over this service — but the writable surface is identical:
`POST /features` accepts them, and their effects live in the same effect
engine (a feat's ASI alternatives are one `ABILITY_SCORE` choice group like
any other feature choice — the feats catalog's response carries no separate
ASI shape). FEAT/OTHER rows are never auto-granted to characters, so they
need no reconciliation, and a held one can't be deleted.

## FeatureEffectsService

`FeatureEffectsService` (in `effects/`, exposed via `FeatureEffectsDep`; a plain class over
`FeatureEffectsRepository`, which holds every query and row write) owns the two write endpoints
above. Both take a row lock on the feature and **diff by row id** against the existing rows
instead of deleting everything and recreating it: an item with an existing id updates that row,
an item with no id creates one, and an existing row whose id is missing from the payload is
deleted — an id that doesn't belong to this feature is a 422. `CharacterFeatureChoice.choice_option_id`
is `ondelete RESTRICT`, so `set_choice_groups` deletes the stored picks of a removed option/group
itself first (the pick reverts to pending); the `IntegrityError` safety net only maps a violation
on `character_feature_choices` to a 409 — every other integrity error is not disguised.

Each write is one `unit_of_work`: diff -> flush -> `has_*` flags (one `UNION ALL` query) ->
`refresh_feature_effect_caches` for the granted characters -> COMMIT -> cache purge. A write that
changes nothing skips the character refresh and the purge. Choice groups are written in two
batches (new groups, then new options) and the existing options' effect rows are loaded with one
query per effect type across all groups.

The `has_static_effects` / `has_choices` columns are the single source for the listings;
`tests/integration/features/features/test_effects_validation.py` pins the invariant that they
always match the effect tables.

Error split: schema-level violations are **422** (Pydantic, plus
`InvalidFeatureEffectDataError` for ids that don't resolve), level/feat-column violations on
PATCH are **400** (`InvalidFeatureSourceException`), a held FEAT/OTHER delete is **409**.
