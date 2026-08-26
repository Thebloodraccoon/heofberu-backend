# Classes catalog (`app/features/classes/`)

Capability-oriented reference catalog for character classes, laid out as a set of
per-capability mini-features instead of one God-Object service. The request/response
schemas live together in `schemas.py` (class-level only — subclass schemas are in
`subclasses/crud/schemas.py`).

## Layout

| Path | Capability | Endpoints |
| --- | --- | --- |
| `crud/` | Class CRUD + composed full read | `GET/POST /classes`, `GET/PATCH/DELETE /classes/{class_id}` |
| `features/` | CLASS-source feature list CRUD | `GET/POST/PATCH/DELETE /classes/features?class_id=...` |
| `skills/` | Available-skills replacement | `PUT /classes/available-skills?class_id=...` |
| `items/` | Starting-equipment list/replace | `GET/PUT /classes/items?class_id=...` |
| `armor/` | Armor proficiencies replace | `PUT /classes/armor-proficiencies?class_id=...` |
| `throws/` | Saving throws replace | `PUT /classes/saving-throws?class_id=...` |
| `weapons/` | Weapon proficiencies replace | `PUT /classes/weapon-proficiencies?class_id=...` |
| `progression/` | Spell-slot table + full 1–20 progression view | `PUT /classes/spell-slots`, `GET /classes/progression` |
| `subclasses/` | Nested subdomain (see below) | `/classes/subclasses/...` |

Root files: `router.py` (assembles all sub-routers under the static `/classes`
prefix), `dependencies.py` (one `Dep` alias per capability: `ClassCrudDep`,
`ClassFeaturesDep`, ...), `cache.py` (`CLASS_CACHE_NAMESPACES` +
`invalidate_class_cache()`), `exceptions.py`, `schemas.py`.

## Conventions

- **Composition over mixins.** `ClassCrudService` extends `CachedService` and composes
  every capability service explicitly in `__init__` (no mixin MRO). `get_by_id`
  returns `ClassFullResponse` — base fields, saving throws/proficiencies/available
  skills/starting items/spell slots, CLASS-source `features`, plus a brief reference to
  each subclass. `create_class` seeds only the simple child rows (saving throws,
  armor/weapon proficiencies, available skills) inside one `_atomic()` transaction;
  features, subclasses, starting items and spell slots are attached afterwards via
  their dedicated endpoints.
- **Shared engine.** The capability services inherit the cross-catalog building blocks
  from `app.features.shared`: `ClassFeatureService(SourceFeatureMixin)` for features,
  `ClassItemsService(SourceItemManagerMixin)` for starting items, and
  `ClassSkillService(SkillsManagerMixin)` for available skills. The class-specific bits
  stay here: source-type pinning (`FeatureSourceType.CLASS`) and the post-commit purge of
  the catalog namespace (`invalidate_class_cache()`) — including an extra purge inside
  `ClassFeatureService._mutate_feature`, because `ClassFullResponse` embeds `features`.
- **Cache.** Every write calls `cache.py:invalidate_class_cache()` after its commit; it
  purges all of `CLASS_CACHE_NAMESPACES = ("classes", "nested_features", "nested_items",
  "characters")` — `characters` because character payloads derive saves/hit dice from
  the class live at response time.
- **Query-style IDs.** All per-feature/per-capability endpoints identify the owning class
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

## Subclasses subdomain conventions (`subclasses/`)

Self-contained capability-oriented subpackage mounted under the static prefix
`/classes/subclasses`:

- `base.py` — `SubclassScopedMixin._get_or_404_for_class`: fetches the raw `Subclass`
  and translates any miss/wrong-class into the parent-scoped `SubclassNotFoundException`
  (404) from the catalog's `exceptions.py`; the subdomain has no `exceptions.py` of its own.
- `crud/` + `features/` — same mini-feature shape as the top level. `SubclassCrudService.get_by_id`
  returns `SubclassFullResponse` (base fields + SUBCLASS-source `features`);
  `SubclassFeatureService` re-implements `_mutate_feature` (duplicated rather than
  inherited from `SourceFeatureMixin`) because its source type is always `SUBCLASS` and its
  source lookup goes through `_get_or_404_for_class`. Both reconcile affected character
  grants inside the write transaction.
- `cache.py` — `invalidate_subclass_cache()` purges `("classes", "nested_features")`,
  since subclasses and their features are embedded in cached class responses.
- `dependencies.py` / `router.py` — `SubclassCrudDep` / `SubclassFeaturesDep`; the
  aggregating router applies `/subclasses` once.
- **URL convention:** every endpoint carries the owning class as the required `class_id`
  query parameter; mutations additionally take `subclass_id` as a query parameter; only
  the detail read keeps the child in the path (`GET /classes/subclasses/{subclass_id}?class_id=...`)
  to avoid colliding with the listing.

The parent's crud service composes the subdomain directly
(`ClassCrudService.subclasses = SubclassCrudService(db)`) for full responses and
create-time wiring.
