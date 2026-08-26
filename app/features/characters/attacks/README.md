# attacks/

Character attack/weapon CRUD (`character`-scoped rows in the `attacks`
table), exposed at `/characters/attacks?character_id=...`.

- `service.py` — `CharacterAttackService`, a `CharacterSubDomainService`
  (inherited GM/owner access check via `get_character_for_user`) that
  delegates persistence to `CharacterAttackRepository`.
- `repository.py` — `CharacterAttackRepository` (`BaseRepository[Attack]`);
  character-scoped queries; create reuses the base method with
  `character_id` injected into the payload by the service.
- `schemas.py` — `AttackCreate` / `AttackUpdate` / `AttackResponse`
  (PATCH semantics: only provided fields change).
- `exceptions.py` — `AttackNotFoundException` (404, character-scoped).

Endpoints: GET/POST/PATCH/DELETE on the single `/attacks` path; per-attack
operations take an additional `attack_id` query parameter.
