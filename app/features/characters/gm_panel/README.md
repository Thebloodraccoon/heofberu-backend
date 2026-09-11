# Character GM Panel (`/characters/gm-panel`)

GM-facing control surface over a single character, split into mini-capabilities
laid out like a capability-oriented catalog (one `router.py`/`service.py`/
`schemas.py` triple — plus a `repository.py` where a table is owned — per
capability). The aggregating root `router.py` applies the static `/gm-panel`
prefix once; every sub-router is a bare `APIRouter()` whose paths carry their
own capability segment.

## Conventions

- **Character identification**: every endpoint takes the owning character as a
  required `character_id` query parameter (`Annotated[int, Query(gt=0)]`).
  Per-row operations additionally take the row's own id as a query parameter
  (`feat_id`, `feature_id`, `item_id`, `adjustment_id`, `skill_id`) — the id of
  the character-scoped grant/stack/choice row, never the reference-catalog id.
- **Access model**: every route is a GM-only write via `GmUserDep`, except three
  read-only endpoints that are GM **or** owner via `CurrentUserDep`:
  `GET /max-level`, `GET /asi`, `GET /items`. The matching player-facing reads
  live in plain character CRUD (`GET /characters/feats`,
  `GET /characters/features`, `GET /characters/stats`).
- **Grant response schemas** live in top-level `characters/schemas.py`
  (`CharacterFeatResponse`, `CharacterFeatureResponse`,
  `SkillProficiencyResponse`) so `crud/` never imports from `gm_panel/`.
- Root files: `dependencies.py` (the `GmPanel*Dep` service aliases),
  `exceptions.py` (ALL panel HTTP exceptions — progression imports from here
  for its level-up ASI path), `validation.py` (ASI-choice/prerequisite checks
  shared by `feats` and progression).

## Capabilities

| Capability | Endpoints | Access | Owns |
|---|---|---|---|
| `feats` | POST/PATCH/DELETE `/feats` | GM only | `CharacterFeatRepository` |
| `features` | POST/DELETE `/features` | GM only | `CharacterFeatureRepository` |
| `items` | GET/POST/PATCH/DELETE `/items` | reads GM/owner, writes GM only | `CharacterItemRepository` + own schemas |
| `asi` | GET/POST/DELETE `/asi` | reads GM/owner, writes GM only | own schemas |
| `hp` | PATCH `/max-hp` | GM only | — |
| `level` | PATCH/GET `/max-level` | reads GM/owner, writes GM only | `CharacterMaxLevelRepository` |
| `proficiencies` | POST/DELETE `/proficiencies/{skills,saving-throws,armor,weapons}`, PATCH `/proficiencies/skills/expertise` | GM only | 4 typed repos + `CharacterProficiencyAuditRepository` |
| `spells` | POST/DELETE `/spells` | GM only | `CharacterGrantedSpellRepository` |

### `feats` — feat grants

POST grants a reference feat outside any level-up flow (201); PATCH changes
the grant's ability-score increase choice; DELETE revokes it (204). A feat
offering ASI options MUST be granted with an explicit
`ability_score_increase_id` — omitting it raises
`FeatAsiChoiceRequiredException` (422), and clearing it via PATCH is likewise
rejected. Every grant/update/remove refreshes the ability-score cache
(`CharacterStatsService`) and re-syncs auto-granted features
(`sync_progression_features`). A grant carrying an ASI choice also writes an
audit row into `character_asi_choices` (`class_level IS NULL`, choice type
FEAT) so the log shows where each stat point came from; the feat's stat
effect reaches the ability-score cache through the granted feature's ASI
effect (`feature_ability_score_effects`), materialized alongside the grant.
The level-up endpoint (`CharacterProgressionService._apply_feat`) writes the
same table through this repository with `source_type=ASI`.

### `features` — feature grants

Records/removes reference features on a character (the referenced feature
itself is immutable). Add/remove refresh the ability-score cache because
features can carry fixed `feature_ability_increases` effects. Progression
auto-grants can be removed here too.

### `items` — inventory

The former standalone `characters/items/` subpackage. Each `character_items`
row is an independent stack, so the same item may be owned several times;
each POST creates its own stack row (`quantity` defaults to 1, 0 allowed).
PATCH applies partial updates (`exclude_unset` semantics) to quantity; there
is no way to change `item_id` — remove the stack and add a new one instead.
`CharacterItemNotFoundException` lives in the root `exceptions.py`.

### `asi` — free-form ±adjustments

GET lists the character's adjustments (`class_level IS NULL` rows only, GM/
owner); POST adds an adjustment as a `character_asi_choices` row with
`class_level IS NULL` (Postgres unique constraint treats NULLs as distinct),
independent of class level and with no +2 level-up budget — negative amounts
allowed. The base ability columns are NEVER touched: counted increments live
in typed `character_asi_choice_increases` child rows and flow into effective
totals through the calculator. A 20 cap IS enforced on the resulting effective
total (raised by feature `new_cap` effects). DELETE reverts one adjustment by
deleting its log row (+ cascade of the child increments) and refreshing the
cache, refusing level-tied rows (`LevelTiedAsiChoiceException`) — those belong
to the level-up flow.

Recorded adjustments/choices also surface to the player as `asi` contributions
via `GET /characters/{character_id}/stats`.

### `hp` — max HP

PATCH `/max-hp` is the ONLY write path for `Character.max_hp` (it is not a
field of the player-reachable `CharacterUpdate`). When the new maximum is
below the current HP pool, `current_hp` clamps DOWN to it; temp HP is
untouched.

### `level` — max-level cap

PATCH/GET `/max-level` on `character_max_levels` (one row per character,
seeded at the starting level on creation and backfilled by migration): the
GM-set cap a character may level up to. Writes can ONLY raise it — a value at
or below the stored maximum (`MaxLevelCanOnlyIncreaseException`) or below the
character's current level (`MaxLevelBelowCharacterLevelException`) is
rejected, and the schema caps it at `CHARACTER_MAX_LEVEL`. The repository is
imported by progression for the level-up gate.

### `proficiencies` — add/remove/expertise across all four proficiency tables

POST/DELETE `/proficiencies/skills`, `/saving-throws`, `/armor`, `/weapons`
grant or revoke a free-form (no feature behind it) proficiency row directly;
PATCH `/proficiencies/skills/expertise?skill_id=...` with `{is_expertise:
bool}` toggles expertise on an EXISTING skill proficiency row (404
`SkillProficiencyNotFoundException` if not proficient — expertise requires
and implies proficiency). Expertise is never derived automatically; clients
read `is_expertise` off the proficiency row and double the proficiency
bonus. Weapon add/remove takes exactly one of `weapon_category`/`item_id`.
Every write appends a row to `character_proficiency_audit_log` (who did
what, when) — the proficiency tables themselves carry no history, so a
removal or a revoked expertise flag would otherwise be silent. The four
per-type repositories are plain classes (not `BaseRepository`) because
skill proficiency has a composite PK `(character_id, skill_id)` and the
others key on a per-character-per-value uniqueness instead of a surrogate id.

Services extend `CharacterSubDomainService` (light character fetch for access
control; `GmPanelHpService` overrides `_light_character_fetch = False` because
it serializes a full `CharacterResponse`). Multi-table writes go through
`_atomic()`.
