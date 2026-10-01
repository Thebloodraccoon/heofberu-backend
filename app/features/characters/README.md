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
| `schemas.py` | Shared domain schemas: `CharacterCreate`/`CharacterUpdate`/`CharacterResponse`, the `PatchModel` base (explicit `null` in a PATCH is a 422 except for fields listed in `nullable_fields`) and the input bounds (`NAME_MAX_LENGTH`, `MONEY_MAX`, `HP_LIMIT`, ...). Bounds live on the input schemas only — `CharacterResponse` stays unconstrained so older stored rows still serialize. Sub-packages import from here — never the reverse. |
| `exceptions.py` | Domain-wide `AppError`s: `CharacterNotFoundException`, `CharacterAccessDeniedException`, `GmOnlyFieldException`, `BackgroundNotFoundException`. |
| `access.py` | Access-control helpers: `is_gm` (GM or founder), `get_character_or_404`, `check_character_access`, the combined `get_character_for_user` (GM or owner, else 403/404) and `ensure_character_access` (same decision from a single `owner_id` lookup, for sub-resources that never read the character). |
| `base.py` | `CharacterSubDomainService` — shared base for sub-domain services: owns the single `CharacterRepository`, the access checks (`get_character_for_user`, `ensure_character_access`) and the transaction helpers (`_atomic()`, `_unit_of_work()`, `_invalidate_character()`). `_light_character_fetch = True` only means "no `populate_existing`" (an instance already in the session is returned as it is); services that need a freshly re-read row override it to `False`. |
| `dependencies.py` | All `Character*Dep` service aliases (`CharacterServiceDep`, `CharacterSpellServiceDep`, ...). |
| `cache.py` | Exact-key invalidation of the cached character response: `character_cache_key`, `invalidate_character_cache(id, db=None)`, `invalidate_characters_cache(ids, db=None)`, `CHARACTER_CACHE_TTL` (300 s). Pass the writing session as `db` to defer the purge until the surrounding `atomic()` block commits (dropped on rollback); there is no namespace/prefix purge and no keyspace scan. |

**Transaction rule:** the service owns the transaction. A multi-step write runs inside `self._atomic()` / `self._unit_of_work()` with `commit=False` repository calls; a single-repository write may rely on the repository's own commit. Routers never commit. Cache purges are scheduled with `self._invalidate_character(id)`, which runs after the commit inside an atomic block and immediately outside one.

### Sub-packages

- `crud/` — the character record itself. `service.py` (`CharacterService`:
  list/get/update/delete, HP, rests, response assembly and the response
  cache), `creation.py` (`CharacterCreationService`: `prepare` validates every
  reference and choice read-only, `persist` writes the character and its
  starting state with `commit=False`; the caller owns the transaction),
  `rules.py` (pure rules: skill/suggestion/equipment-choice validation,
  starting HP, HP delta/clamping), `repository.py` (owner lookup,
  `FOR UPDATE` fetch, HP and slot-usage writes), `schemas.py` (HP/rest
  payloads), `exceptions.py`, `router.py`.
- `ability_score/` — effective ability scores and the hit-dice lookup: pure
  `calculator.py` (no DB; also builds the per-source breakdown),
  `repository.py` for the `character_ability_scores` cache table (atomic
  `INSERT ... ON CONFLICT DO UPDATE`) and the batched bonus-source queries,
  and `CharacterStatsService` as the single decision point for *when* the
  cache is recomputed.
- `attacks/` — weapon/attack rows on the sheet (at most 100 per character).
- `conditions/` — conditions applied to a character (not part of the cached
  response, so they never purge it). The add is an atomic
  `INSERT ... ON CONFLICT DO NOTHING`; a duplicate is a 409.
- `items/` — read-only inventory listing (`GET /characters/{id}/items`); the
  stack repository is shared with the GM panel, which owns all writes.
- `level/` — only `CharacterMaxLevelRepository` (the GM-set level-up cap row),
  used by creation, the GM panel and progression.
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
  point-rebuild endpoint (`POST /characters/{id}/rebuild`): a full
  class/subclass/race(required)/subrace/background + base-ability-score
  swap that recomputes skill proficiencies and source-owned features,
  requires one `asi_choices` entry per ASI level already reached
  (replacing the character's prior ASI/feat history at those levels),
  validates and sets the caller-supplied `max_hp` against the new
  class/level's allowed range, recomputes spell slots, and clears known
  spells — while leaving level, notes, personality, backstory, inventory,
  GM-granted feats and GM ASI adjustments (`class_level IS NULL`) untouched.
  Layout: `service.py` (use cases), `asi.py` (applying an ASI/feat and writing
  the log), `background.py` (skills/equipment of a late background),
  `rebuild.py`, `rules.py` (pure HP/ASI rules), `feature_sync.py`
  (progression-feature reconciliation). Every write is owned by the service:
  the character row is locked with `SELECT ... FOR UPDATE` (a double
  level-up/set_background/rebuild is serialized), the ability-score cache is
  refreshed in the same transaction and Redis is purged after COMMIT; routers
  never commit. A feat on an ASI level (level-up and rebuild) needs
  `Feature.min_level <= class_level`, the chosen ASI option must stay within
  the cap of 20 and the prerequisite is checked against the effective scores;
  a rebuild feat that offers ASI options without `ability_score_increase_id`
  is a 422, and its other choice groups stay pending (`GET /grants/pending`).
  Input bounds: ids <= 2147483647, `feature_choices`/`answers` <= 50,
  `hit_points_gained` <= 50, rebuild `max_hp` <= 1000, `skill_ids` <= 30.
- `grants/` — answering a feature's choice groups. Authorization lives in
  `FeatureGrantService` (its methods take `current_user`); `PATCH .../choices`
  is one service transaction with the cache purge after COMMIT;
  `resolve_grants_choices` is the level-up batch (trees loaded in one query,
  features without `has_choices` skipped).
- `gm_panel/` — GM-only panel under `/characters/gm-panel`: feat grants
  (with mandatory ASI choice when offered), feature grants, inventory
  (items), free-form ±ASI adjustments, max-HP edit, the per-character
  level-up cap (`max-level`), and skill-expertise toggle.
- The original-vs-computed stats overview (with a per-source contribution
  breakdown on every ability) is a **player-facing** read under
  `GET /characters/{id}/stats` (see `crud/router.py`), not part of the GM
  panel.

## One-shot creation contract

`POST /characters` (`crud/service.create_character`, steps in
`crud/creation.py`) is the ONLY path that creates a character. Everything is
derived server-side:

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
- **Backstory** is not accepted in the payload: when a background is chosen
  its description (capped at `BACKSTORY_MAX_LENGTH`) is stored as the
  backstory; afterwards it is edited via `PUT /characters/{id}/backstory`
  (`content` is required; `""` clears it), isolated in `character_backstories`
  and never cached.
- **`inspiration`** is a 0-13 point stockpile (not 5e's plain boolean),
  defaults to `0`. The plain character PATCH lets a player only keep or lower
  it; raising it is GM-only (403 `GmOnlyFieldException`).
- Spell slots for level 1 are applied immediately; features, the ability-score
  cache row (computed once and reused for the starting-HP math) and starting
  equipment (class + background, aggregated into one stack per item) are
  granted in the same `_atomic()` transaction. Every reference is loaded once
  (`get_by_id`), not checked with `exists_by_id` and loaded again.

## Update, HP and rest

- `PATCH /characters/{id}` is bounded (name 1-200 chars, money <= int32,
  AC/shield/speed <= 1000, free text length-capped) and rejects explicit
  `null` with a 422. `current_hp` is clamped to `max_hp`.
- `PATCH /characters/{id}/hp` and `POST /characters/{id}/rest` (long) read the
  row `SELECT ... FOR UPDATE` inside one atomic block, so concurrent
  damage/healing is applied sequentially instead of overwriting each other.
  A long rest restores HP, clears temp HP and resets spell-slot usage in the
  same transaction; the cache purge happens only after the commit.
- Mixing `delta` with absolute values (or sending neither) stays a 400.

## Read-path conventions

- `GET /characters` and `GET /characters/{id}` are fully **read-only**: the
  `character_ability_scores` cache is read **as-is**, never recomputed on a
  read. Write paths that can affect scores refresh it (create, feat
  grant/update/remove, level-up ASI, subrace/background setup).
- Only **hit dice** are looked up on every read (`ability_score/service.py`,
  a two-column query) — they follow the class reference row, so no write path
  keeps them in sync. `speed`, `armor_class` and `shield` are plain editable
  columns (speed is seeded from the race at creation); there is no derived AC.
- `GET /characters/{id}` reads the character row once for the access check
  and reuses it on a cache miss; the assembled response is cached under the
  exact key `<CACHE_PREFIX>:characters:<id>` for 300 s. Access control is
  never cached.
- Listings order by `name` then `id` (stable pagination) and read the
  ability-score rows and hit dice in one batched query each.
- `GET /characters/{id}/stats` is the only read path that **recomputes**
  per-ability totals fresh (never the cache) — it pairs each ORIGINAL base
  value with its COMPUTED total plus the per-source contribution breakdown
  ("what is calculated from what"), via
  `CharacterStatsService.compute_breakdown`. Player/GM/owner readable.

## ASI-choice log as counted source

Level-up ASIs and GM ±adjustments **never touch the base ability columns**
— their points live as typed `character_asi_choice_increases` child rows of
`character_asi_choices` and are counted by
`CharacterStatsRepository.get_asi_increases_many` →
`CharacterAbilityScoreCalculator.compute`. Legacy pre-rework rows carry
`applied_to_base = True` and are excluded from the count. Effective totals
are floored at 1. The pure `calculator.resolve_ability_caps` (feature effects
with `new_cap` lift a cap above 20) is not wired into any validation yet.
