# Skills Catalog

Reference catalog for the `Skill` entity: each skill has a unique display `name`, a governing ability (`AbilityScore`), and an optional description (e.g. "Stealth", DEX).

## Layout

- `crud/` — the single capability: `repository.py` (`SkillRepository`), `service.py` (`SkillCrudService`), `schemas.py`, `router.py` (bare router).
- `cache.py` — cache namespace tuples.
- `dependencies.py` — `SkillCrudDep` service dependency.
- `router.py` — assembles the surface under `/skills`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/skills` | open | Paginated list (`Page[SkillGetAllResponse]`, no description), ordered by name. Filters: `search` (name, case-insensitive, max 100 chars), repeatable `ability`. |
| GET | `/skills/{skill_id}` | open | Full `SkillResponse`. |
| POST | `/skills` | GM | Duplicate `name` → 400. |
| PATCH | `/skills/{skill_id}` | GM | Partial update; duplicate `name` → 400; explicit `null` → 422. |
| DELETE | `/skills/{skill_id}` | Founder | Blocked with 409 while referenced anywhere (see below). |

Duplicates answer **400** (`RecordAlreadyExistsError`, platform-wide), not 409. `name` is 1..100 characters, whitespace-trimmed.

## Service composition

`SkillCrudService` extends `CachedService[...]` over `SkillRepository`. Extra behaviour:

- Uniqueness on `name` (`unique_fields=["name"]`).
- A delete guard (`is_in_use`, one `EXISTS` statement) over `race_skills`, `class_available_skills`, `background_skills`, the unified `character_proficiencies` rows of type `SKILL` (cascading FK), and `feature_skill_proficiency_effects` (RESTRICT FK). `delete` locks the skill row first (`SELECT ... FOR UPDATE`), so a reference inserted between the guard and the DELETE waits instead of being cascaded away silently.

The catalog does NOT manage granted-skill lists themselves — those are owned by the parent catalogs (races/classes/backgrounds) via the shared `app/features/shared/skills/` mixins.

## Cache

`cache.py`: `SKILL_OWN_CACHE_NAMESPACES = ("skills",)` and `SKILL_DEPENDENT_CACHE_NAMESPACES` (classes, races, backgrounds, features, feats and every `*_features` list; derived from `CACHE_DEPENDENTS["skills"]` in `app/core/cache/namespaces.py`). Class/race/background details embed `SkillResponse` rows and `effects_summary` renders skill names, so:

- **update** purges all of them (`SKILL_CACHE_NAMESPACES`, the service's `cache_namespaces`);
- **create** and **delete** purge only `skills` (a new skill isn't referenced yet; a skill can only be deleted once nothing references it).

All purges run after the commit.
