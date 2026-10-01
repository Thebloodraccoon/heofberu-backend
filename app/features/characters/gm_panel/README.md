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
| `asi` | GET/POST/DELETE `/asi` | reads GM/owner, writes GM only | `GmAsiRepository` |
| `hp` | PATCH `/max-hp` | GM only | `GmHpRepository` |
| `level` | PATCH/GET `/max-level` | reads GM/owner, writes GM only | `CharacterMaxLevelRepository` |
| `proficiencies` | POST/DELETE `/proficiencies/{skills,saving-throws,armor,weapons}`, PATCH `/proficiencies/skills/expertise` | GM only | `CharacterProficiencyGmRepository` |
| `spells` | POST/DELETE `/spells` | GM only | `CharacterGrantedSpellRepository` |

### `feats` — feat grants

POST grants a reference feat outside any level-up flow (201); PATCH changes
the grant's ability-score increase choice; DELETE revokes it (204). Unlike
PATCH (which still rejects clearing an already-set choice —
`FeatAsiChoiceRequiredException`, 422), POST no longer requires
`ability_score_increase_id` up front even for a feat offering ASI options:
omitting it leaves the feat's ASI choice group pending, like any other
choice group, answerable later via PATCH or the generic
choice-answering/pending-grant endpoints. Every grant/update/remove refreshes the ability-score cache
(`CharacterStatsService.refresh(commit=False)`) and re-syncs auto-granted features
(`sync_progression_features`) in the SAME transaction as the grant (a failing refresh rolls the grant back);
the character payload purge runs after that commit. A grant carrying an ASI choice also writes an
audit row into `character_asi_choices` (`class_level IS NULL`, choice type
FEAT) so the log shows where each stat point came from; the feat's stat
effect reaches the ability-score cache through the granted feature's ASI
effect (`feature_ability_score_effects`), computed on read from the grant.
The level-up endpoint (`AsiChoiceService.apply_feat` in `progression/asi.py`) writes the
same table through this repository with `source_type=ASI`. The response
carries no dedicated ASI field — a picked ASI option surfaces in the
generic `choices` list (`ability_effects`), same as any other feature's
choice group; `FeatBriefResponse` also carries `effects_summary`.

### `features` — feature grants

Records/removes reference features on a character (the referenced feature
itself is immutable). Add/remove refresh the ability-score cache (same transaction) because
features can carry fixed `feature_ability_increases` effects. Progression
auto-grants can be removed here too.

### `items` — inventory

The former standalone `characters/items/` subpackage. Each `character_items`
row is a stack (POST `quantity` 1..1 000 000, default 1; PATCH may set 0..1 000 000). POST merges into the
character's existing stack of that `item_id` (the earliest one, if somehow
more than one exists) by adding the new quantity onto it (a merged stack above 1 000 000 is a 400); only when the
character has no stack of that item yet does POST create a new row. PATCH
applies partial updates (`exclude_unset` semantics) to quantity; there is no
way to change `item_id` — remove the stack and add a new one instead.
`CharacterItemNotFoundException` lives in the root `exceptions.py`.

### `asi` — free-form ±adjustments

GET lists the character's adjustments (`class_level IS NULL` rows, filtered in
SQL, oldest first; GM/owner); POST adds an adjustment as a
`character_asi_choices` row with `class_level IS NULL`, independent of class
level and with no +2 level-up budget — negative amounts allowed. Request
bounds: `increases` has 1..6 entries (no duplicate ability), each `amount` is
non-zero and within ±30. The base ability columns are NEVER touched: counted
increments live in typed `character_asi_choice_increases` child rows and flow
into effective totals through the calculator. A cap of 30
(`MAX_ABILITY_SCORE_CAP`) IS enforced on the resulting effective total.

POST is one transaction under the character's row lock (`characters/locking.py`):
write the row, recompute the totals ONCE and upsert the cache table
(`stats_service.refresh(commit=False)`), check every touched total against the
cap and roll everything back if it is exceeded. Two concurrent adjustments can
therefore not jointly exceed the cap and the cache never lags the log. DELETE
reverts one adjustment (cascade of the child increments) and refreshes the
cache in the same transaction, refusing level-tied rows
(`LevelTiedAsiChoiceException`) — those belong to the level-up flow.

Recorded adjustments/choices also surface to the player as `asi` contributions
via `GET /characters/{character_id}/stats`.

### `hp` — max HP

PATCH `/max-hp` is the ONLY write path for `Character.max_hp` (it is not a
field of the player-reachable `CharacterUpdate`); `0 <= max_hp <= 10 000`.
The write is a single `UPDATE ... SET max_hp = :m, current_hp = LEAST(current_hp, :m)
RETURNING`, so a concurrent heal/damage is never overwritten with a stale
value. Temp HP is untouched.

### `level` — max-level cap

PATCH/GET `/max-level` on `character_max_levels` (one row per character,
seeded at the starting level on creation and backfilled by migration): the
GM-set cap a character may level up to. Writes can ONLY raise it — a value at
or below the stored maximum (`MaxLevelCanOnlyIncreaseException`) or below the
character's current level (`MaxLevelBelowCharacterLevelException`) is
rejected, and the schema caps it at `CHARACTER_MAX_LEVEL`. The write validates
under the character's row lock and a missing row (cap = current level) is
seeded directly at the new value only after validation passed. The repository
is imported by progression for the level-up gate.

### `proficiencies` — add/remove/expertise across all four proficiency kinds

POST/DELETE `/proficiencies/{skills,saving-throws,armor,weapons}` grant or
revoke a free-form proficiency through the GM layer; PATCH
`/proficiencies/skills/expertise?skill_id=...` with `{is_expertise: bool}`
sets expertise on a skill the character already has (404
`SkillProficiencyNotFoundException` otherwise). Weapon add/remove takes exactly
one of `weapon_category`/`item_id`; unknown `skill_id`/`item_id` are 404.

The GM layer is at most one `source_type=GM` row per (character, proficiency)
and never touches other sources' rows. The resolution rules live in ONE place,
`characters/proficiencies/resolver.py`, shared by the read surface
(`GET /characters/{id}/proficiencies`) and these writes: a GM `REVOKE` vetoes
every other source; any other entry grants; a GM `GRANT` row with an explicit
`is_expertise` decides expertise alone (so the GM can also clear expertise a
class/feature gives), otherwise expertise is the OR of the sources. A plain
GM grant stores `is_expertise = NULL` (no decision).

Each write loads the proficiency's rows (`get_rows`) and the feature/feat grants
that give it (`feature_entries`: ONE targeted `UNION ALL` query over the effect
tables, not the whole effect tree of every grant) once, decides in memory and
applies the minimal GM-layer change (`apply`): when the wanted outcome already
follows from the other sources no GM row is needed (an existing one is deleted);
otherwise the GM row is `GRANT` (nothing else grants it) or `REVOKE` (a veto) and
is updated in place or inserted. Re-granting after a veto therefore always
works, including when the vetoed source has since disappeared. The response is
built from the in-memory result, so there is no post-commit read.

### `spells` — GM-granted spells

POST/DELETE `/spells` hand out / take back a spell (`gm_spells`) with no
eligibility check. The duplicate check and the insert run in one transaction
under the character's row lock, so concurrent grants of the same spell cannot
race into a unique violation (clean 409). The response is built from the
fetched spell (no re-select after the insert).

## Transactions and cache

Every write is owned by its service: `unit_of_work(db)` wraps the whole use
case (lock, validate, write, recompute), repositories only flush, and the
character cache purge is scheduled with `uow.after_commit(...)` so it runs only
after a successful COMMIT and is dropped on rollback. A validation failure
inside the block rolls back and nothing was written. Known spells
(`characters/spells`) follow the same rule: the per-level cap (`total` slots) is
checked under the character lock.
