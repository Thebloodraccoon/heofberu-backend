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
├── router.py            # /feats: crud + the shared features/effects router (mounted under /feats)
├── dependencies.py      # FeatCrudDep
├── cache.py             # FEAT_CACHE_NAMESPACES + invalidate_feat_cache()
└── crud/                # schemas (incl. ASI flatten view), FeatRepository view, FeatCrudService, router
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/feats` | open | Cached paginated `Page[FeatGetAllResponse]` (id/name/min_level/`has_static_effects`/`has_choices`), ordered by name; `search` on name. |
| GET | `/feats/{feat_id}` | open | Full `FeatResponse` — base + prerequisite fields + `choice_groups` + `static_groups` + `has_static_effects`/`has_choices`/`effects_summary`, mirroring `FeatureResponse`. |
| POST | `/feats` | GM | Top-level feat creation with optional embedded `ability_score_increases` (`{ability, amount}`); duplicate `name` → 409. Written as a FEAT-source `Feature`; the ASI list is seeded as one choice group (`pick_count=1`) with one option per alternative (each option carrying a `FeatureAbilityScoreEffect`), mirroring the legacy confirmed-pick semantics. |
| PATCH | `/feats/{feat_id}` | GM | Update base/prerequisite fields only — see the dedicated note on ASI below. |
| DELETE | `/feats/{feat_id}` | Founder | Blocked with 409 while any character still holds a grant of the feat. |
| GET/PUT | `/feats/{feat_id}/effects` | open / GM | Read / full-replace the feat's **fixed** effects (all six types), GM write. |
| GET/PUT | `/feats/{feat_id}/choice-groups` | open / GM | Read / full-replace the feat's choice-group tree (e.g. Skilled's "pick 3 skills", Resilient's "+1 to an ability score"). |

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
  option's `ability_effects[0]` off `FeatResponse.choice_groups` instead.
- A character grant's `ability_score_increase_id` points at the picked
  option's `AbilityEffectItem` row id (`choice_groups[].options[].ability_effects[].id`),
  so ASI row ids must never be rewritten.

## Write semantics & caches

- `FeatCrudService` extends `BaseService` over `Feature`: `get_all` /
  `get_by_id` / `update` are **overridden** (not inherited) to scope rows to
  `source_type=FEAT` and serialize through the shared `_to_feat_brief`/
  `_to_feat_response` helpers. `FeatRepository`'s eager loads are the full
  engine effect tree (`feature_summary_loads()`) for both listing and detail,
  since `has_static_effects`/`has_choices`/`static_groups` read every
  fixed-effect relationship and the choice-group tree.
- PATCH (`update_feat`) touches **base/prerequisite fields only** — it never
  edits ASI options. Change ability-score choices via
  `PUT /feats/{feat_id}/choice-groups` and fixed ASI via
  `PUT /feats/{feat_id}/effects` (there is no dedicated
  `ability-score-increases` endpoint anymore; the effects surface is the
  unified engine).
- Every write purges BOTH the `feats` namespace (`FEAT_CACHE_NAMESPACES =
  ("feats",)`) and the shared `features` namespace — `GET /features` reads the
  same underlying table.
- FEAT rows are standalone: never auto-granted to characters, and their writes
  trigger no character reconciliation (they are picked by players).

## Relationship to `/features`

The central `/features` catalog (`POST /features`, per-source feature list
invalidations) remains the single feature manager; a FEAT row written here is
queryable there too. This catalog exists purely to give feats their own
discoverable endpoints, their legacy ASI response shape, and FEAT-only
prerequisite columns (`FeatPrerequisiteFields`, shared between
`features/crud/schemas.py` and `feats/crud/schemas.py`).