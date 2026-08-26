# progression/

Character progression: level-up flow, subclass/subrace/background setup,
the rebuild stub, and feature auto-grant reconciliation
(`/characters/progression/...?character_id=...`, `POST /characters/rebuild`).

- `service.py` — `CharacterProgressionService`
  (`CharacterSubDomainService`):
  - Level-up (`POST /progression/level-up`): gated by the GM-set cap in
    `character_max_levels` (`can-level-up` reports
    `{can_level_up, current_level, max_level}`). HP gain defaults to
    `die // 2 + 1 + CON mod`, floored at ≥1 (5e minimum); an explicit
    `hit_points_gained` must fit `[1, die + CON]`. An ASI level
    (4/8/12/16/19) REQUIRES a `choice` (ASI increments or a feat);
    a feat offering ASI options requires an explicit
    `ability_score_increase_id` (422 otherwise). ASI points live ONLY as
    typed `character_asi_choices` child rows (base ability columns are
    never touched). The whole level bump runs in one `_atomic()`
    transaction: level, choice, HP, feature sync, spell-slot re-application.
  - Setup endpoints (`PATCH /progression/subclass|subrace|background`):
    fill a still-unset slot; background can be set ONCE only (409
    otherwise) and grants features + deduplicated skills + starting
    equipment like creation did. Subclass/subrace may be set or cleared
    (must belong to the current class/race). All refresh the stat cache
    because granted features can carry fixed ability effects.
  - Rebuild (`POST /characters/rebuild`): placeholder, responds 501.
- `feature_sync.py` — `sync_progression_features` reconciles
  `character_features` against the class/subclass/race/subrace/background
  feature set (level NULL or ≤ current level); NEVER commits — callers
  wrap it in their own transaction. `reconcile_characters_for_source`
  re-runs it for every character affected by a source's feature edit;
  `refresh_feature_effect_caches` refreshes stat caches after a feature's
  fixed ability effects change.
- `repository.py` — `CharacterASIChoiceRepository`: the audit/counted log
  of resolved ASI choices (`class_level NULL` = GM adjustment).
- `schemas.py` — request/response schemas (`LevelUpRequest` with the
  discriminated `ASIChoice | FeatChoice` union, `CanLevelUpResponse`, ...);
  ASI budget validated at the schema layer (+1..+2 total, no duplicates).
- `exceptions.py` — 501 rebuild stub, 409 background-already-set,
  400 max-level / choice-required / choice-not-allowed / ASI-cap / HP-gain
  errors.
