# conditions/

Attach/detach of active conditions on a character
(`character_conditions` table), exposed at
`/characters/conditions?character_id=...`.

- `service.py` — `CharacterConditionService`, a
  `CharacterSubDomainService` (GM/owner access via
  `get_character_for_user`). Add rejects duplicates (409); every write
  purges the character cache. EXHAUSTION is validated against the merged
  row on update (`exhaustion_level` required 1–6 for EXHAUSTION,
  rejected otherwise).
- `repository.py` — `CharacterConditionRepository`
  (`BaseRepository[CharacterCondition]`): list/get/add/update/remove of
  active-condition rows.
- `schemas.py` — `CharacterConditionAdd` (schema-level exhaustion
  validator) / `CharacterConditionUpdate` / `CharacterConditionResponse`.
- `exceptions.py` — `CharacterConditionNotFoundException` (404),
  `CharacterConditionAlreadyExistsException` (409),
  `InvalidConditionException` (400).

Endpoints: GET/POST/PATCH/DELETE on the single `/conditions` path;
per-condition operations take the `condition` enum as a query parameter.
The condition itself is fixed once added — remove and re-add to change it.
