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
| GET | `/feats` | open | Cached paginated `Page[FeatGetAllResponse]` (id/name/min_level/`ability_score_increases`), ordered by name; `search` on name. |
| GET | `/feats/{feat_id}` | open | Full `FeatResponse` — base + prerequisite fields + `ability_score_increases` (legacy flattened view) + `choice_groups` + all six effect lists. |
| POST | `/feats` | GM | Top-level feat creation with optional embedded `ability_score_increases` (`{ability, amount}`); duplicate `name` → 409. Written as a FEAT-source `Feature`; the ASI list is seeded as one choice group (`pick_count=1`) with one option per alternative (each option carrying a `FeatureAbilityScoreEffect`), mirroring the legacy confirmed-pick semantics. |
| PATCH | `/feats/{feat_id}` | GM | Update base/prerequisite fields only — see the dedicated note on ASI below. |
| DELETE | `/feats/{feat_id}` | Founder | Blocked with 409 while any character still holds a grant of the feat. |
| GET/PUT | `/feats/{feat_id}/effects` | open / GM | Read / full-replace the feat's **fixed** effects (all six types), GM write. |
| GET/PUT | `/feats/{feat_id}/choice-groups` | open / GM | Read / full-replace the feat's choice-group tree (e.g. Skilled's "pick 3 skills", Resilient's "+1 to an ability score"). |

## How the ASI view works

`feature_ability_score_effects` deserializes into the legacy
`ability_score_increases` shape (`AbilityScoreIncreaseResponse`:
id/ability/amount) that the API and character grants have always consumed.
Rules that make this work:

- A feat's ASI alternatives live in **at most one** choice group
  (`pick_count=1`) whose options each carry a single `AbilityEffectItem` —
  e.g. "+2 STR or +2 DEX" is ONE group with two options, and that guarantee is
  schema-enforced in the effect engine.
- The flattened ordering is the engine's *display* order (`sort_order`,
  then id), which is stable after a read-back.
- A character grant's `ability_score_increase_id` points at the picked option's
  `AbilityEffectItem` row id, so ASI row ids must never be rewritten.

## Write semantics & caches

- `FeatCrudService` extends `BaseService` over `Feature`: `get_all` /
  `get_by_id` / `update` are **overridden** (not inherited) because
  `ability_score_increases` is a computed flattening, not a same-named ORM
  relationship.
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