# Spells Catalog

Reference catalog of spells. A spell carries its scalar detail fields (school,
level, cast time, range, components, attack/save/damage/healing data) plus
four availability dimensions stored as M2M association tables:
`spell_classes`, `spell_subclasses`, `spell_races`, `spell_subraces`.

## Capabilities / Endpoints

Mounted under `/spells` by `router.py` (one `include_router` per capability,
same `Spells` tag):

| Capability | Endpoints |
| --- | --- |
| `crud/` | `GET ""` (paginated, heavily filterable listing), `GET /{spell_id}`, `POST ""` (GM), `PATCH /{spell_id}` (GM), `DELETE /{spell_id}` (Founder) |
| `availability/` | `PUT /spells/{spell_id}/classes`, `PUT /spells/{spell_id}/subclasses`, `PUT /spells/{spell_id}/races`, `PUT /spells/{spell_id}/subraces` — full-replace of each availability dimension (GM) |

The spell is identified via a **path** parameter (`{spell_id}`) on all
availability endpoints. Request body is `{class_ids: [...]}`,
`{subclass_ids: [...]}`, etc.; unknown ids -> 400, repeated ids collapse to one,
`[]` clears the restriction. Each `set_*` returns the full `SpellResponse`.
Deps live in `dependencies.py` (`SpellCrudDep`, `SpellAvailabilityDep`);
`exceptions.py` holds `SpellNotFoundException`.

## Layout and transactions

- `crud/repository.py` — `SpellRepository` plus the single table of availability dimensions
  (`AVAILABILITY_DIMENSIONS`: field, label, catalog model, association table, child FK).
  Everything that touches the association tables lives here: `set_availability` (replace one
  dimension), `get_dimension_members` (resolve ids), `load_availability` (the listing's links for
  a page of spells in **one** `UNION ALL` query, ordered by child name in SQL — no re-sort in
  Python). `get_plain` is the bare-row fetch used by delete.
- `crud/service.py` — `SpellCrudService` (extends `CachedService`). `create_spell` resolves the
  ids, then writes the spell row and its availability in one `_atomic()` transaction (the cache
  purge is deferred to after the COMMIT). `update` is one transaction too.
- `availability/service.py` — `SpellAvailabilityService`: the four PUTs share one `_replace`
  (404 check, resolve ids, replace in `_atomic()`, purge `spells` after the COMMIT, return the
  full `SpellResponse`). A failed write rolls the previous links back.

## Write validation (422)

`SpellCreate`/`SpellUpdate` reject unknown keys and bound every value: `name` 1-300 chars,
texts <= 20 000, `range_value` 0..1 000 000, dice counts 1..100, <= 500 availability ids
(each 1..2^31-1). `SpellCreate` also requires dice count and type together (damage and healing
alike) and a `MATERIAL` component whenever `material`/`is_material_consumed` is set. `SpellUpdate`
rejects an explicit `null` for any NOT NULL column (omit the field to keep it); nullable columns
(`range_value`, `attack_type`, `material`, ...) can still be cleared with `null`.

## Cache Invalidation

`cache.py` owns the matrix. `SPELL_CACHE_NAMESPACES = ("spells",)` is purged by every write.
A spell's **name** is rendered into other catalogs' cached payloads (the `effects_summary` of the
features that grant it), so a **rename** also purges `SPELL_NAME_DEPENDENT_NAMESPACES`:
`features`, `feats`, the five `*_features` lists, `classes`, `races`, `backgrounds` and
`characters`. Deleting a spell only purges `spells` (a spell referenced by a feature effect can't
be deleted).

The reverse direction (renaming/deleting a class/subclass/race/subrace purges `spells`, whose list
embeds `{id, name}` of the available classes/subclasses/races/subraces) is declared once in
`app/core/cache/namespaces.py` (`CACHE_DEPENDENTS`) and applied by those modules' `cache.py`
(`*_CRUD_CACHE_NAMESPACES`, `*_DELETE_*`).

## Notable Rules

- **Empty list on a dimension = unrestricted** on that dimension. There is no
  "available to nobody" state per dimension.
- **Character eligibility ANDs the four restricted dimensions**: a spell is
  castable by a character only if it passes the class, subclass, race, and
  subrace checks (each unrestricted dimension passes automatically). See
  `characters/spells/eligibility.py`.
- A spell can't be deleted (409) while a character knows it (`character_spells`), the GM granted
  it (`character_granted_spells`) or a feature effect grants it (`feature_spell_grant_effects`).
- The known-cantrip cap is a `"CANTRIP"` row in a class's spell-slot
  progression table (`PUT /classes/{class_id}/spell-slots?class_level=` with
  `{"spell_level": "CANTRIP"}`) — that lives in the classes catalog, not
  here; without such a row no character of that class can learn any cantrip.
