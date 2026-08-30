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
| `availability/` | `PUT /spells/classes|subclasses|races|subraces?spell_id=` — full-replace of each availability dimension (GM) |

The spell is identified via the required `spell_id` query parameter on all
availability endpoints (query-style IDs). Deps live in `dependencies.py`
(`SpellCrudDep`, `SpellAvailabilityDep`); `exceptions.py` holds
`SpellNotFoundException`.

## Service Composition & Create Seeding

`crud/service.py:SpellCrudService` extends `CachedService` and composes
`SpellAvailabilityService` in `__init__`. `create_spell` seeds association
rows at create time inside one `_atomic()` transaction: each provided
availability list is resolved through `resolve_ids` (400 on unknown ids),
then written through the availability service's `set_*_for_spell(...,
commit=False)` variants next to the new `Spell` row. Empty or omitted lists
mean the spell stays unrestricted on that dimension.

`get_all` is overridden to build the cached listing WITHOUT materializing
full `Spell` rows — column-selected scalars plus one join query per
availability dimension per page (`_load_availability`).

## Cache Invalidation

`cache.py` owns `invalidate_spell_cache()` purging `SPELL_CACHE_NAMESPACES =
("spells",)`. Every write — catalog CRUD and availability replacement alike —
calls it after commit; the crud service also declares it as
`cache_namespaces`.

## Notable Rules

- **Empty list on a dimension = unrestricted** on that dimension. There is no
  "available to nobody" state per dimension.
- **Character eligibility ANDs the four restricted dimensions**: a spell is
  castable by a character only if it passes the class, subclass, race, and
  subrace checks (each unrestricted dimension passes automatically). See
  `characters/spells/eligibility.py`.
- The known-cantrip cap is a `"CANTRIP"` row in a class's spell-slot
  progression table (`PUT /classes/spell-slots` with
  `{"spell_level": "CANTRIP"}`) — that lives in the classes catalog, not
  here; without such a row no character of that class can learn any cantrip.
