# spells/

Known spells and spell slots for a character
(`/characters/spells?character_id=...`).

Slot semantics:

- Slot totals are class-derived ONLY (`ClassSpellSlotProgression`,
  applied on create via `_apply_spell_slot_progression` and re-applied on
  level-up) and never client-writable — there are no spend/restore
  endpoints. The legacy `used` column stays 0.
- `GET /spells` returns one payload `{spell_slots: [{spell_level, total}],
  spells: [...]}` (`CharacterSpellsResponse`).
- A level's `total` doubles as the cap on known spells of that level —
  this applies to CANTRIP too (a class's known-cantrip cap is a
  `"CANTRIP"` row in its slot progression table). Remove a known spell to
  free its slot.

Files:

- `service.py` — `CharacterSpellService` (`CharacterSubDomainService`;
  GM/owner access check). Read returns slots + known spells; add validates
  existence/duplicate, then delegates eligibility to the checker; writes
  purge the character cache.
- `eligibility.py` — `CharacterSpellEligibilityChecker`: ANDs the four
  restricted dimensions (`available_classes` / `available_subclasses` /
  `available_races` / `available_subraces`; empty list = unrestricted on
  that dimension), then checks slot capacity (known count < total at the
  spell's level; missing entry = 0).
- `repository.py` — `CharacterSpellSlotRepository` (slot upsert/sync,
  incl. `commit=False` mode for creation-time transactions) and
  `CharacterSpellRepository` (known-spell rows, Spell eager-loaded).
- `schemas.py` — `SpellSlotResponse` / `CharacterSpellAdd` /
  `CharacterSpellResponse` / `CharacterSpellsResponse`.
- `exceptions.py` — not-found (404), already-known (409),
  restriction/slot-capacity violations (400).
