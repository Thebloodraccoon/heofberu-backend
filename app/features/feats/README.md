# Feats Catalog

Reference catalog for the `Feat` entity — origin/general feats with base fields (name, description, ability-score prerequisite trio, `min_level`) plus their ASI choices: the `feat_ability_score_increases` child rows ("choose one ability: STR/DEX/CON..." à la Resilient). A feat is de facto its OWN feature — its content lives in its description.

## Layout

- `crud/` — catalog CRUD + seeding: `repository.py` (`FeatRepository`), `service.py` (`FeatCrudService`), `router.py` (bare router).
- `asi/` — the ASI-choice capability: `service.py` (`FeatAsiService`), `router.py` (bare router).
- `../feats/schemas.py` — all request/response schemas for both capabilities (catalog-root level).
- `../feats/cache.py`, `../feats/dependencies.py` (`FeatCrudDep`, `FeatAsiDep`), `../feats/exceptions.py` (`FeatNotFoundException`, 404), `../feats/router.py` — both sub-routers mounted under `/feats`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/feats` | open | Paginated list (`Page[FeatGetAllResponse]`: id/name/min_level + `ability_score_increases`); `search` on name. |
| GET | `/feats/{feat_id}` | open | Full `FeatResponse` including ASI choices; cached as a single unit. |
| POST | `/feats` | GM | Optional nested `ability_score_increases` seeded atomically with the row; duplicate `name` → 409. |
| PATCH | `/feats/{feat_id}` | GM | Base fields only — ASI choices have their own PUT endpoint; duplicate `name` → 409. |
| DELETE | `/feats/{feat_id}` | Founder | Cascades ASI choices away; blocked with 409 while granted to any character (`character_feats`). |
| PUT | `/feats/ability-score-increases?feat_id=` | GM | Full replace of the ASI choice list (empty list clears); duplicate abilities → 422. |

## Notable rule: feats own NO features

Since migration `a9d4f2e8b1c7` feats are not a feature source: the FEAT `FeatureSourceType` was removed from the Python enum and `features.feat_id` was dropped. There are no feature endpoints or nested-feature payloads for feats anywhere in this catalog — the feat's benefit text is simply its description.

## Service composition

The crud service composes the asi capability explicitly in `__init__` (`self._asi = FeatAsiService(db)`) — no mixin MRO:

- `create_feat` wraps the `Feat` insert and the optional ASI seeding in one `_atomic()` transaction, delegating the child-row write to `FeatAsiService.set_ability_score_increases_for_feat(commit=False)`.
- `FeatAsiService.set_ability_score_increases` is the public full-replace write behind `PUT /feats/ability-score-increases`; the repository does the actual replace via `replace_child_rows(FeatAbilityScoreIncrease, ...)` with a deferrable commit.
- Reads and delete come straight from `CachedService`; uniqueness on `name` → 409 via `unique_fields`.

## Cache

Feats serve only the `feats` namespace (`FEAT_CACHE_NAMESPACES = ("feats",)`): they embed no features and no other catalog caches embed feat detail beyond the listing. Both services declare it as `cache_namespaces` and writes additionally call `invalidate_feat_cache()` explicitly after commit; `create_feat` then re-warms the cache immediately so the next GET doesn't race into a cold read.
