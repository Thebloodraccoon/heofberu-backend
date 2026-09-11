# Classes catalog (`app/features/classes/`)

Capability-oriented reference catalog for character classes, laid out as a set of
per-capability mini-features instead of one God-Object service. There is no
top-level `schemas.py` — each capability owns its own `schemas.py` (its
Update/Response types, plus any private `_validate_unique_*` helper its
validators need), mirroring `backgrounds/`. `crud/schemas.py` holds only the
class-identity schemas (`ClassBase`/`Create`/`Update`/`Response`/`GetAllResponse`)
and assembles `ClassResponse` by importing each capability's own Response type
(`SavingThrowResponse` from `throws/schemas.py`, `ArmorProficiencyResponse`
from `armor/schemas.py`, etc) — the same aggregation shape as
`backgrounds/crud/schemas.py`. Subclass schemas are in
`../subclasses/crud/schemas.py`.

## Layout

| Path | Capability | Endpoints |
| --- | --- | --- |
| `crud/` | Class identity schemas + CRUD + composed full read | `GET/POST /classes`, `GET/PATCH/DELETE /classes/{class_id}` |
| `features/` | CLASS-source feature list (read-only) | `GET /classes/features?class_id=...` |
| `skills/` | Available-skills replacement | `PUT /classes/{class_id}/available-skills` |
| `items/` | Starting-equipment list/replace | `GET/PUT /classes/{class_id}/items` |
| `armor/` | Armor proficiencies replace | `PUT /classes/{class_id}/armor-proficiencies` |
| `throws/` | Saving throws replace | `PUT /classes/{class_id}/saving-throws` |
| `weapons/` | Weapon proficiencies replace | `PUT /classes/{class_id}/weapon-proficiencies` |
| `progression/` | Spell-slot table + full 1–20 progression view | `PUT /classes/{class_id}/spell-slots`, `GET /classes/{class_id}/progression` |
| `../subclasses/` | Nested subdomain (see below) | `/classes/subclasses/...` |

Root files: `router.py` (assembles all sub-routers under the static `/classes`
prefix), `dependencies.py` (one `Dep` alias per capability: `ClassCrudDep`,
`ClassFeaturesDep`, ...), `cache.py` (`CLASS_CACHE_NAMESPACES` +
`invalidate_class_cache()`), `exceptions.py`. No root `schemas.py` — see above.

## Conventions

- **Composition over mixins.** `ClassCrudService` extends `CachedService` and composes
  the capability services `update_class`/`get_by_id` need explicitly in `__init__`
  (no mixin MRO): `_throws`/`_armor`/`_weapons` back `update_class`'s full-replace
  PATCH fields, `_features` + `self.subclasses` back `get_by_id`. `get_by_id` returns
  `ClassResponse` (it doubles as the create/update response too) with the class's own
  CLASS-source `features` and a brief reference to each subclass folded in.
  `create_class` writes base fields only — saving throws, armor/weapon proficiencies,
  available skills, features, subclasses, starting items, and spell slots are all
  attached afterwards via their own dedicated endpoints (mirrors races/backgrounds).
- **Shared engine.** The feature write endpoints (POST/PATCH/DELETE) have been removed
  from per-catalog surfaces — features are managed centrally through the features
  catalog. `ClassFeatureService` now provides read-only listing via `list_features`.
  Starting items use `ClassItemsService(SourceItemManagerMixin)`, and available skills
  use `ClassSkillService(SkillsManagerMixin)`.
- **Cache.** Every write calls `cache.py:invalidate_class_cache()` after its commit; it
  purges all of `CLASS_CACHE_NAMESPACES = ("classes", "class_features", "features",
  "nested_items", "characters")` — `class_features` is the class's own feature-list
  cache (also purged directly by the central `FeatureCrudService`), `features` the
  central by-id feature cache, and `characters` because character payloads derive
  saves/hit dice from the class live at response time.
- **Query-style IDs.** All per-capability endpoints identify the owning class
  by a required `class_id` query parameter; routers are bare `APIRouter()`s assembled by
  the catalog `router.py`.

## Spell-slot progression (and the CANTRIP row)

`progression/service.py` owns two things:

1. **`PUT /classes/spell-slots?class_id=...&class_level=...`** — full replace of one
   level's slot rows (`{slots: [{spell_level, slots}]}`); any `spell_level` omitted is
   reset to 0. `class_level` must be within 1–20 (400 otherwise). Character slot totals
   are derived ONLY from this table (`ClassSpellSlotProgression`) — they are applied on
   character creation and re-applied on level-up, never client-writable.
2. **`GET /classes/progression?class_id=...`** — the derived 1–20 table: per level the
   proficiency bonus, `{spell_level: slots}`, CLASS-source features gained, and
   SUBCLASS-source features gained (aggregated across subclasses).

**CANTRIP is just another row:** a class's known-cantrip cap is a `"CANTRIP"` entry in
the same spell-slot progression table (e.g. `PUT /classes/spell-slots?class_id=...&class_level=3`
with `{"slots": [{"spell_level": "CANTRIP", "slots": 2}]}`). Without a CANTRIP row at a
given class level, no character of that class can learn any cantrip at that level.

## Subclasses subdomain conventions (`../subclasses/`)

Self-contained capability-oriented subpackage mounted under the static prefix
`/classes/subclasses`:

- `base.py` — `SubclassScopedMixin._get_or_404_for_class`: fetches the raw `Subclass`
  and translates any miss/wrong-class into the parent-scoped `SubclassNotFoundException`
  (404) from the catalog's `exceptions.py`; the subdomain has no `exceptions.py` of its own.
- `crud/` — `SubclassCrudService.get_by_id` returns `SubclassResponse` (it doubles as
  the create/update response too), with the subclass's own SUBCLASS-source `features`
  folded in. The `GET /subclasses` listing returns `SubclassGetAllResponse` (lightweight
  rows), also embedded in `ClassResponse.subclasses`.
- `features/` — read-only feature listing for SUBCLASS-source features.
- `cache.py` — `invalidate_subclass_cache()` purges
  `("classes", "subclass_features", "features")`, since subclasses and
  their features are embedded in cached class responses.
- `dependencies.py` / `router.py` — `SubclassCrudDep` / `SubclassFeaturesDep`; the
  aggregating router applies `/subclasses` once.
- **URL convention:** every endpoint carries the owning class as the required `class_id`
  query parameter; mutations additionally take `subclass_id` as a query parameter; only
  the detail read keeps the child in the path (`GET /classes/subclasses/{subclass_id}?class_id=...`)
  to avoid colliding with the listing.

The parent's crud service composes the subdomain directly
(`ClassCrudService.subclasses = SubclassCrudService(db)`) for full responses and
create-time wiring.
