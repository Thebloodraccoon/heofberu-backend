# Characters Domain

The player-facing heart of the app: character sheets and everything hanging
off them. FastAPI + SQLAlchemy 2.0, laid out as a **compound feature** — a
handful of shared root files plus self-contained sub-packages, each a
mini-feature (`router.py` / `service.py` / `repository.py` / `schemas.py`,
bare `APIRouter()`; the root `router.py` applies the `/characters` prefix).

## Layout

### Root files (this folder)

| File | Role |
| --- | --- |
| `router.py` | Aggregates the six child routers under `/characters`, one `include_router` per child, tags declared here once. |
| `schemas.py` | Shared domain schemas: `CharacterCreate`/`CharacterUpdate`/`CharacterResponse` plus the feat/feature grant responses (`CharacterFeatResponse`, `CharacterFeatureResponse`). `CharacterFeatResponse` embeds the resolved ASI (`ability_score_increase`: `{id, ability, amount}`) so a feat read shows which ability it improved. Sub-packages import from here — never the reverse. |
| `exceptions.py` | Domain-wide `AppError`s: `CharacterNotFoundException`, `CharacterAccessDeniedException`, `BackgroundNotFoundException`. |
| `access.py` | Access-control helpers: `get_character_or_404`, `check_character_access`, and the combined `get_character_for_user` (GM or owner, else 403/404). Almost every character operation starts with one of these. |
| `base.py` | `CharacterSubDomainService` — shared base for sub-domain services: owns the single `CharacterRepository`, exposes `_atomic()` and the access-checked `get_character_for_user`. Defaults to the **light** character fetch (`_light_character_fetch = True` → scalar columns only); services that serialize a full `CharacterResponse` override it to `False`. |
| `dependencies.py` | All `Character*Dep` service aliases (`CharacterServiceDep`, `CharacterSpellServiceDep`, ...). |
| `cache.py` | `invalidate_character_cache(character_id)` + `CHARACTER_CACHE_NAMESPACE`. The detail read is cached under a flat key the namespace-prefix pattern can't match, so both the prefix purge and the exact key delete are needed. |

### Sub-packages

- `crud/` — the character record itself: list/get/create/update/delete, HP
  updates, rests, and the one-shot creation contract (see below).
  `CharacterService` is the core service.
- `ability_score/` — effective ability scores and derived combat stats:
  pure `calculator.py` (no DB), `repository.py` for the
  `character_ability_scores` cache table and bonus-source queries, and
  `CharacterStatsService` as the single decision point for *when* the cache
  is recomputed.
- `attacks/` — weapon/attack rows on the sheet.
- `conditions/` — conditions applied to a character.
- `backstory/` — the character's backstory, isolated in its own table
  (`character_backstories`) and served ONLY through dedicated endpoints
  (`GET/PUT /characters/{id}/backstory`). Because it can run several pages of
  free text (up to `BACKSTORY_MAX_LENGTH` = 12000 chars, ~4 pages of Word), it
  is deliberately excluded from the cached `CharacterResponse` and is never
  cached — reads hit the DB directly through the owner/GM access check. It is
  also not part of `CharacterCreate`/`CharacterUpdate`.
- `spells/` — known spells + slot totals (class-derived only, no
  spend/restore endpoints).
- `progression/` — level-up, subclass/subrace/background setup,
  progression-feature sync, the ASI-choice log repositories, and the
  501-stubbed rebuild endpoint.
- `gm_panel/` — GM-only panel under `/characters/gm-panel`: feat grants
  (with mandatory ASI choice when offered), feature grants, inventory
  (items), free-form ±ASI adjustments, max-HP edit, the per-character
  level-up cap (`max-level`), and skill-expertise toggle.
- The original-vs-computed stats overview (with a per-source contribution
  breakdown on every ability) is a **player-facing** read under
  `GET /characters/{id}/stats` (see `crud/router.py`), not part of the GM
  panel.

## One-shot creation contract

`POST /characters` (`crud/service.create_character`) is the ONLY path that
creates a character. Everything is derived server-side:

- **Level pinned to 1**, `temp_hp=0`; the payload has no `level`/HP fields
  and `CharacterCreate` sets `extra="forbid"`, so stale clients sending
  removed fields get a 422.
- **No origin feat**: there is no mandatory starting feat anymore — creation
  carries no `feat_id`/`ability_score_increase_id` (`CharacterCreate` rejects
  them as extra fields with a 422). Characters start with zero feats and zero
  ASI-choice audit rows; feats come only from GM grants (`gm_panel/feats`) or
  ASI-level choices during progression. The feat-grant path still validates
  existence, explicit ASI choice when the feat offers options (else 422),
  ability cap, and prerequisite.
- **Max-level row seeded** at the starting level in the same transaction:
  the character cannot level up until a GM raises its cap via the GM panel.
- **Skills merged and deduplicated** across three sources: the validated
  class choices from `skill_ids` (each must be in the class's
  `available_skills`, total ≤ `skill_choice_count`) plus the background's
  and the race's granted skills, written with `is_expertise=False`
  (expertise is a GM-panel edit afterwards).
- **Starting HP fully server-derived**: hit-die faces + effective CON
  modifier, clamped to ≥1; `current_hp` starts equal to it.
- **Level-up fully heals** (`progression/level_up`): HP gain is added to
  `max_hp` (die + CON), then `current_hp` is restored to the new maximum
  and `temp_hp` is cleared.
- **Saving throws are never stored** on the character — they are derived
  from the class on every response (the table was dropped by migration).
- **Backstory is not part of creation** — it is written afterwards via the
  dedicated `PUT /characters/{id}/backstory` endpoint (and read via
  `GET /characters/{id}/backstory`), isolated in `character_backstories` and
  never cached.
- **`inspiration`** (5e's per-session boolean) defaults to `False` and is
  editable via the plain character PATCH.
- Spell slots for level 1 are applied immediately; features and starting
  equipment (class + background, aggregated into one stack per item) are
  granted in the same `_atomic()` transaction.

## Read-path conventions

- `GET /characters` and `GET /characters/{id}` are fully **read-only**: the
  `character_ability_scores` cache is read **as-is**, never recomputed on a
  read. Write paths that can affect scores refresh it (create, feat
  grant/update/remove, level-up ASI, subrace/background setup).
- Only **hit dice and speed** are computed on the fly
  (`ability_score/service.py`) — they follow the class/race reference rows,
  so no write path keeps them in sync. `armor_class`/`shield` are plain
  editable columns; there is no derived AC.
- `GET /characters/{id}/stats` is the only read path that **recomputes**
  per-ability totals fresh (never the cache) — it pairs each ORIGINAL base
  value with its COMPUTED total plus the per-source contribution breakdown
  ("what is calculated from what"), via
  `CharacterStatsService.compute_breakdown`. Player/GM/owner readable.

## ASI-choice log as counted source

Level-up ASIs and GM ±adjustments **never touch the base ability columns**
— their points live as typed `character_asi_choice_increases` child rows of
`character_asi_choices` and are counted by
`CharacterStatsRepository.get_asi_increases` →
`CharacterAbilityScoreCalculator.compute`. Legacy pre-rework rows carry
`applied_to_base = True` and are excluded from the count. Effective totals
are floored at 1; per-ability caps resolve through
`CharacterStatsService.resolve_ability_caps` (feature effects with
`new_cap` can lift a cap above 20).
