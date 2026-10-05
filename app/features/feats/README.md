# Feats Catalog (`app/features/feats/`)

**A feat IS a Feature.** Since the unified-feature migration (`c7c6838`) feats
are ordinary `Feature` rows with `source_type=FEAT`, stored in the central
feature engine's tables — there are no legacy feat tables anymore and no
`asi/` subpackage. This catalog is a thin FEAT-scoped view over that engine:
`FeatRepository` is a FEAT-pinned `FeatureRepository`, `FeatCrudService`
wraps `FeatureCrudService`-style CRUD, and the write surface for a feat's
mechanical effects IS the shared feature effect engine (reused verbatim).

## Layout

```
feats/
├── router.py            # /feats: crud + the shared features/effects router (mounted under /feats, guarded by require_feat)
├── dependencies.py      # FeatCrudDep, require_feat
├── cache.py             # FEAT_CACHE_NAMESPACES
├── exceptions.py        # FeatNotFoundException (used by characters), FeatPrerequisiteIncompleteError
└── crud/                # schemas, FeatRepository view, FeatCrudService, router
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/feats` | open | Cached paginated `Page[FeatGetAllResponse]` (id/name/min_level/`has_static_effects`/`has_choices`), ordered by name; `search` on name. |
| GET | `/feats/{feat_id}` | open | Full `FeatResponse` — base + prerequisite fields + `choice_groups` + `static_groups` + `has_static_effects`/`has_choices`/`effects_summary`, mirroring `FeatureResponse`. |
| POST | `/feats` | GM | Top-level feat creation with optional embedded `ability_score_increases` (`{ability, amount}`); duplicate `name` → 409. Written as a FEAT-source `Feature`; the ASI list is seeded as one choice group (`pick_count=1`) with one option per alternative (each option carrying a `FeatureAbilityScoreEffect`), mirroring the legacy confirmed-pick semantics. |
| PATCH | `/feats/{feat_id}` | GM | Update base/prerequisite fields only (see ASI note below); duplicate `name` → 409; explicit `null` for a NOT NULL field → 422; a prerequisite with only ability or only minimum score → 422. |
| DELETE | `/feats/{feat_id}` | Founder | Blocked with 409 while any character still holds a grant of the feat. |
| GET / POST / PATCH / DELETE | `/feats/{feat_id}/effects[/{effect_type}/{effect_id}]` | open / GM | Read / add / change one / remove one **fixed** effect, same contract as `/features/{id}/effects`. 404 when the id is not a feat. |
| GET / POST / PATCH / DELETE | `/feats/{feat_id}/choice-groups[/{group_id}[/options/{option_id}[/effects/...]]]` | open / GM | Read / point-edit the feat's choice groups, options and option effects (e.g. Skilled's "pick 3 skills"), same contract as `/features/{id}/choice-groups`. 404 when the id is not a feat. |

Input bounds: `name` 1..200 (trimmed), `prerequisite_minimum_score` 1..30, ASI `amount` 1..10 (at most 6 alternatives). `prerequisite_ability` and `prerequisite_minimum_score` are set together or not at all. Duplicates answer **400** (`RecordAlreadyExistsError`, platform-wide).

## How the ASI view works

A feat's ASI alternatives are just a `choice_groups` entry like any other
feature choice — there is no dedicated ASI response shape anymore. Rules
that make this work:

- A feat's ASI alternatives live in **at most one** choice group
  (`pick_count=1`) whose options each carry a single `AbilityEffectItem` —
  e.g. "+2 STR or +2 DEX" is ONE group with two options, and that guarantee is
  schema-enforced in the effect engine.
- `feat_ability_score_effects` (`app/features/feats/crud/repository.py`)
  flattens that group's options into an ordered list of
  `FeatureAbilityScoreEffect` rows for internal use — character-grant
  validation (`app/features/characters/feats/validation.py`) and the
  ASI-picked-on-grant response (`FeatAbilityScoreIncreaseResponse`) — but the
  feat catalog response itself no longer exposes it as a flat field; read the
  option's `effects` group with `effect_type: "ability"` off `FeatResponse.choice_groups` instead.
- A character grant's `ability_score_increase_id` points at the picked
  option's `AbilityEffectItem` row id (`choice_groups[].options[].effects[ability].items[].id`),
  so ASI row ids must never be rewritten.

## Write semantics & caches

- `FeatCrudService` extends `CachedService` over `Feature`; the repository scopes every query (`get_by_id`, `get_row`, `exists_by_id`, `count`, `get_brief`) to `source_type=FEAT`. The listing column-selects brief fields plus the denormalized `has_static_effects`/`has_choices` (real `Feature` columns, kept in sync by every effect/choice-group write — see `FeatureEffectsService._refresh_effect_flags` and `FeatRepository.set_ability_score_increases`). The full effect tree (`feature_summary_loads()`) is loaded only by `get_by_id`, because `static_groups`/`effects_summary` read every fixed-effect relationship and the choice-group tree.
- `update` and `delete` read the bare row (`get_row`), then `update` loads the tree once to build the response; `delete` never loads it.
- PATCH touches **base/prerequisite fields only** — it never edits ASI options. Change ability-score choices via `/feats/{feat_id}/choice-groups/...` and fixed ASI via `/feats/{feat_id}/effects/...`.
- Name uniqueness among FEAT rows is checked in code (`features.name` has no unique constraint). A concurrent duplicate that slips through and trips a unique index (see the migration request) is translated to the same `RecordAlreadyExistsError`.
- Delete: `is_in_use` blocks it (409) while any character holds the feat. `character_features.feature_id` cascades, so the feature row is locked (`SELECT ... FOR UPDATE`) before the guard — a concurrent grant waits instead of being wiped.
- Every write purges `FEAT_CACHE_NAMESPACES = ("feats", "features")` after the commit (`GET /features` reads the same table). Skill/item renames purge `feats` from their side (effect summaries render their names).
- FEAT rows are standalone: never auto-granted to characters, and their writes trigger no character reconciliation (they are picked by players).

## Relationship to `/features`

The central `/features` catalog (`POST /features`, per-source feature list
invalidations) remains the single feature manager; a FEAT row written here is
queryable there too. This catalog exists purely to give feats their own
discoverable endpoints and FEAT-only
prerequisite columns (`FeatPrerequisiteFields`, shared between
`features/crud/schemas.py` and `feats/crud/schemas.py`).