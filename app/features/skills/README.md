# Skills Catalog

Reference catalog for the `Skill` entity: each skill has a stable `key`, a display `name`, a governing ability (`AbilityScore`), and an optional description (e.g. "Stealth", DEX).

## Layout

- `crud/` — the single capability: `repository.py` (`SkillRepository`), `service.py` (`SkillCrudService`), `schemas.py`, `router.py` (bare router).
- `../skills/cache.py` — cache namespaces + invalidation helper.
- `../skills/dependencies.py` — `SkillCrudDep` service dependency.
- `../skills/router.py` — assembles the surface under `/skills`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/skills` | open | Paginated list (`Page[SkillGetAllResponse]`, no description). Filters: `search` (name/key, case-insensitive), repeatable `ability`. |
| GET | `/skills/{skill_id}` | open | Full `SkillResponse`. |
| POST | `/skills` | GM | 409 on duplicate `key`. |
| PATCH | `/skills/{skill_id}` | GM | Partial update; duplicate `key` → 409. |
| DELETE | `/skills/{skill_id}` | Founder | Blocked with 409 while referenced anywhere (see below). |

## Service composition

The skills catalog is a simple catalog: one capability only. `SkillCrudService` extends `CachedService[...]` over `SkillRepository` and adds no composed sub-services — its extra behavior lives in two places:

- Uniqueness on `key` before create/update (`unique_fields=["name", "key"]`) → 409 via the data layer.
- A delete guard (`is_in_use`) checking every table whose FK is `ON DELETE RESTRICT`: `race_skills`, `class_available_skills`, `background_skills` M2M rows and `character_skill_proficiencies`. The base `CachedService.delete` triggers it through `check_in_use_on_delete=True`.

Note the catalog does NOT manage granted-skill lists themselves — those are owned by the parent catalogs (races/classes/backgrounds) via the shared `app/features/shared/skills/` mixins.

## Cache

`SKILL_CACHE_NAMESPACES = ("skills", "classes", "races", "backgrounds")`. Every write purges all four through `invalidate_skill_cache()`: class/race/background cached detail responses embed `SkillResponse` rows, so a skill rename must not leave stale names there. The service declares the same tuple as `cache_namespaces` so inherited `CachedService` writes purge automatically.
