# Classes Catalog (`app/features/classes/`)

Capability-oriented reference catalog for character classes, laid out as a set
of per-capability mini-features instead of one God-Object service. There is no
top-level `schemas.py` — each capability owns its own `schemas.py` (its
Update/Response types, plus any private `_validate_unique_*` helper its
validators need), mirroring `backgrounds/`. `crud/schemas.py` holds only the
class-identity schemas (`ClassBase`/`Create`/`Update`/`Response`/`GetAllResponse`)
and assembles `ClassResponse` by importing each capability's own Response type
(`SavingThrowResponse` from `throws/schemas.py`, `ArmorProficiencyResponse`
from `armor/schemas.py`, etc). Subclass schemas live in the separate
`app/features/subclasses/` catalog — subclasses are NOT a subdomain of this
package anymore.

## Layout

| Path | Capability | Endpoints |
| --- | --- | --- |
| `crud/` | Class identity schemas + CRUD + composed full read | `GET/POST /classes`, `GET/PATCH/DELETE /classes/{class_id}` |
| `features/` | CLASS-source feature list (read-only) | `GET /classes/{class_id}/features` |
| `skills/` | Available-skills replacement | `PUT /classes/{class_id}/available-skills` |
| `items/` | Starting-equipment list/replace + choice groups | `GET/PUT /classes/{class_id}/items`, `GET/PUT /classes/{class_id}/choice-groups` |
| `armor/` | Armor proficiencies replace | `PUT /classes/{class_id}/armor-proficiencies` |
| `throws/` | Saving throws replace | `PUT /classes/{class_id}/saving-throws` |
| `weapons/` | Weapon proficiencies replace | `PUT /classes/{class_id}/weapon-proficiencies` |
| `progression/` | Spell-slot table + full 1–20 progression view | `PUT /classes/{class_id}/spell-slots?class_level=`, `GET /classes/{class_id}/progression` |
| `image/` | Class catalog image | `PUT/DELETE /classes/{class_id}/image` |

Root files: `router.py` (assembles all sub-routers under the static `/classes`
prefix), `dependencies.py` (one `Dep` alias per capability: `ClassCrudDep`,
`ClassFeaturesDep`, ..., `ClassImageDep`), `cache.py` (`CLASS_CACHE_NAMESPACES`
+ `invalidate_class_cache()`), `exceptions.py`. No root `schemas.py` — see above.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/classes` | open | Paginated `Page[ClassGetAllResponse]` (id/name/hit_dice/image_url + embedded `subclasses`), ordered by name; `search` on name. |
| GET | `/classes/{class_id}` | open | Full `ClassResponse` — base fields + saving throws/armor/weapon proficiencies + available skills + starting items + choice groups + spell-slot rows + CLASS-source `features` + brief `subclasses`; cached as one unit. |
| POST | `/classes` | GM | Base fields only (`name`, `hit_dice`, `skill_choice_count`, `spellcasting_ability` required — `null` for non-casters, `description`, `image_url`); duplicate `name` → 409. |
| PATCH | `/classes/{class_id}` | GM | Base fields + optional full-replace `saving_throws`/`armor_proficiencies`/`weapon_proficiencies` lists; duplicate `name` → 409. |
| DELETE | `/classes/{class_id}` | Founder | Removes child rows; blocked with 409 while characters still reference the class. |
| PUT | `/classes/{class_id}/available-skills` | GM | Full replace; duplicate/unknown ids → 400/422; duplicates rejected at schema layer. |
| GET/PUT | `/classes/{class_id}/items` | open / GM | List / full-replace starting equipment (`{items: [{item_id, quantity}]}`); unknown ids → 400. |
| GET/PUT | `/classes/{class_id}/choice-groups` | open / GM | List / full-replace starting-equipment choice-group tree (`{choice_groups: [{pick_count, sort_order, options: [{item_id, quantity}]}]}`). |
| PUT | `/classes/{class_id}/armor-proficiencies` | GM | Full replace. |
| PUT | `/classes/{class_id}/saving-throws` | GM | Full replace. |
| PUT | `/classes/{class_id}/weapon-proficiencies` | GM | Full replace. |
| PUT | `/classes/{class_id}/spell-slots?class_level=` | GM | Full replace of one level's slot rows. |
| GET | `/classes/{class_id}/progression` | open | Derived 1–20 table (proficiency bonus, slots, class + subclass features per level). |
| PUT | `/classes/{class_id}/image` | GM | Multipart upload/replace (JPEG/PNG/WebP/GIF, max 5 MB) → `{"image_url"}`. |
| DELETE | `/classes/{class_id}/image` | GM | Clears `image_url` and removes the stored object. |

All capability routers identify the owning class by a **path** parameter
(`/{class_id}/...`), consistent with races/backgrounds.

## Conventions

- **Composition over mixins.** `ClassCrudService` extends `CachedService` and
  composes the capability services `update_class`/`get_by_id` need explicitly
  in `__init__` (no mixin MRO): `_throws`/`_armor`/`_weapons` back
  `update_class`'s full-replace PATCH fields; `_features` + `self.subclasses`
  (a `SubclassCrudService` from the separate subclasses catalog) back
  `get_by_id`. `create_class` writes base fields only — saving throws,
  armor/weapon proficiencies, available skills, features, subclasses, starting
  items, choice groups, and spell slots are all attached afterwards via their
  own dedicated endpoints (mirrors races/backgrounds).
- **Shared engine.** Feature write endpoints (POST/PATCH/DELETE) live only on
  the central `/features` catalog. `ClassFeatureService` is a read-only cached
  listing. Starting items use `ClassItemsService(SourceItemManagerMixin)`
  (delegating to the shared `NestedSourceItemService`, which also owns the
  choice-group tree writes), and available skills use
  `ClassSkillService(SkillsManagerMixin)`.
- **Cache.** Every write calls `cache.py:invalidate_class_cache()` after its
  commit; it purges all of `CLASS_CACHE_NAMESPACES = ("classes",
  "class_features", "features", "nested_items", "characters")` — `class_features`
  is the class's own feature-list cache (also purged directly by the central
  `FeatureCrudService`), `features` the central by-id feature cache,
  `nested_items` the shared starting-equipment listings, and `characters`
  because character payloads derive saves/hit dice from the class live at
  response time.

## Spell-slot progression (and the CANTRIP row)

`progression/service.py` owns two things:

1. **`PUT /classes/{class_id}/spell-slots?class_level=...`** — full replace of
   one level's slot rows (`{slots: [{spell_level, slots}]}`); any `spell_level`
   omitted is reset to 0. `class_level` must be within 1–20 (400 otherwise).
   Character slot totals are derived ONLY from this table
   (`ClassSpellSlotProgression`) — they are applied on character creation and
   re-applied on level-up, never client-writable.
2. **`GET /classes/{class_id}/progression`** — the derived 1–20 table: per
   level the proficiency bonus, `{spell_level: slots}`, CLASS-source features
   gained, and SUBCLASS-source features gained (aggregated across the
   subclasses catalog's rows).

**CANTRIP is just another row:** a class's known-cantrip cap is a `"CANTRIP"`
entry in the same spell-slot progression table (e.g.
`PUT /classes/{class_id}/spell-slots?class_level=3` with
`{"slots": [{"spell_level": "CANTRIP", "slots": 2}]}`). Without a CANTRIP row
at a given class level, no character of that class can learn any cantrip at
that level.

## Subclasses

Subclasses are a **separate catalog** mounted at `/subclasses` with an optional
`class_id` filter — see `app/features/subclasses/README.md`.
`ClassResponse.subclasses` (and the listing's `ClassGetAllResponse.subclasses`)
embed `SubclassGetAllResponse` rows, so class reads (and the shared `classes`
cache namespace) are invalidated by every subclass write too
(`SUBCLASS_CACHE_NAMESPACES` includes `"classes"`).