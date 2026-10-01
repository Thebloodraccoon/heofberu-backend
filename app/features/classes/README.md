# Classes Catalog (`app/features/classes/`)

Reference catalog of character classes, split into small per-capability packages.
Each capability owns its `schemas.py` (Update/Response types); `crud/schemas.py`
holds the class-identity schemas and assembles `ClassResponse` from the
capabilities' response types. Subclasses are a separate catalog
(`app/features/subclasses/`).

## Layout

| Path | Capability | Endpoints |
| --- | --- | --- |
| `crud/` | Class identity schemas, CRUD, repository (`ClassRepository`) | `GET/POST /classes`, `GET/PATCH/DELETE /classes/{class_id}` |
| `proficiencies/` | Saving throws, armor and weapon proficiencies — one generic full-replace service/router (`ProficiencyKind` descriptors in `kinds.py`) | `PUT /classes/{class_id}/{saving-throws,armor-proficiencies,weapon-proficiencies}` |
| `skills/` | Available-skills replacement | `PUT /classes/{class_id}/available-skills` |
| `items/` | Starting equipment list/replace + choice groups | `GET/PUT /classes/{class_id}/items`, `GET/PUT /classes/{class_id}/choice-groups` |
| `progression/` | Spell-slot table + derived 1-20 view | `PUT /classes/{class_id}/spell-slots?class_level=`, `GET /classes/{class_id}/progression` |
| `features/` | CLASS-source feature list (read-only) | `GET /classes/{class_id}/features` |
| `image/` | Class catalog image | `PUT/DELETE /classes/{class_id}/image` |

Root files: `router.py` (mounts every sub-router under `/classes`), `dependencies.py`
(one `Dep` alias per capability), `service_base.py` (`ClassScopedService`, the base of
the capability services), `schema_utils.py` (validation helpers shared with the
subclasses schemas), `cache.py`, `exceptions.py`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/classes` | open | Paginated `Page[ClassGetAllResponse]` (id/name/hit_dice/image_url + embedded `subclasses`), ordered by name; `search` on name. Cached. |
| GET | `/classes/{class_id}` | open | Full `ClassResponse`: base fields, saving throws/armor/weapon proficiencies, available skills, starting items, choice groups, spell-slot rows, CLASS-source `features`, brief `subclasses`. Cached as one unit. |
| POST | `/classes` | GM | Base fields only. `name` 1-100 chars, `skill_choice_count` 0-20, `description` <= 10000, `image_url` absolute http(s) <= 512; `spellcasting_ability` required (`null` for non-casters). Duplicate `name` -> 400. |
| PATCH | `/classes/{class_id}` | GM | Base fields + optional full-replace `saving_throws`, in one transaction. Explicit `null` is rejected (422) except for `spellcasting_ability` (clears it). Duplicate `name` -> 400. |
| DELETE | `/classes/{class_id}` | Founder | Cascades to child rows/subclasses/features; 409 while characters reference the class. |
| PUT | `/classes/{class_id}/available-skills` | GM | Full replace; unknown ids -> 400, duplicates -> 422. |
| GET/PUT | `/classes/{class_id}/items` | open / GM | List / full-replace starting equipment. |
| GET/PUT | `/classes/{class_id}/choice-groups` | open / GM | List / full-replace the choice-group tree. |
| PUT | `/classes/{class_id}/{armor-proficiencies,weapon-proficiencies,saving-throws}` | GM | Full replace. |
| PUT | `/classes/{class_id}/spell-slots?class_level=` | GM | Full replace of one level's slot rows; `class_level` 1-20 and `slots` >= 0 (422 otherwise). |
| GET | `/classes/{class_id}/progression` | open | Derived 1-20 table (proficiency bonus, slots, class features, subclass features with their `subclass_id`). Cached. |
| PUT/DELETE | `/classes/{class_id}/image` | GM | Multipart upload (JPEG/PNG/WebP/GIF, max 5 MB) / clear. |

Every sub-resource `PUT` and `PATCH` answers with the same full `ClassResponse` as
`GET /classes/{class_id}`.

## Conventions

- **Reads reuse the eager-loaded row.** `ClassRepository.default_load_options` loads
  every child collection plus `features` and `subclasses`; `GET /classes/{id}` and the
  mutation responses serialize that row once (no second feature/subclass query).
  Writes that only touch the class's own columns use `ClassRepository.get_row`
  (bare row). `ClassRepository.get_by_id` is also used by the characters flows.
- **One transaction owner.** `update_class` wraps the row update and the saving-throw
  replacement in `_unit_of_work()` (`BaseRepository.update(commit=False)` only
  flushes); single-step writes let the repository commit. Cache purges are
  scheduled after the commit and dropped on rollback.
- **Capability services** extend `ClassScopedService`: one `ClassRepository`, the
  `ClassResponse` schema, `cache_namespaces`. Only `ClassCrudService` is a `CachedService`.
- **Duplicate names** raise `RecordAlreadyExistsError` (HTTP 400).

## Cache

`cache.py` defines exactly which namespaces each kind of write purges:

| Write | Purged |
| --- | --- |
| skills / proficiencies / spell slots / image | `classes` |
| create / update (PATCH) | `classes`, `spells` (spell listings embed class names) |
| items, choice groups | `classes`, `nested_items` |
| delete | `classes`, `class_features`, `subclass_features`, `features`, `nested_items`, `spells` (cascade) |
| `hit_dice` actually changed by PATCH | additionally the cached payloads of that class's characters only (`invalidate_characters_cache(ids)`) |

`classes` holds the class detail/listing, the progression table and the subclass
detail/listing. Central feature writes purge `classes` and `class_features`
themselves (`features/cache.py`). Character payloads depend on a class only through
`hit_dice`, which is why `characters` is not part of the class namespaces.

## Spell-slot progression (and the CANTRIP row)

1. **`PUT /classes/{class_id}/spell-slots?class_level=...`** — full replace of one
   level's slot rows (`{slots: [{spell_level, slots}]}`); omitted spell levels are reset
   to 0. Character slot totals are derived only from this table.
2. **`GET /classes/{class_id}/progression`** — loads only the class name, the slot rows
   and the CLASS/SUBCLASS features with their effect trees (not the full class graph).

**CANTRIP is just another row:** a class's known-cantrip cap is a `"CANTRIP"` entry in the
same table. Without a CANTRIP row at a level, no character of that class can learn
cantrips at that level.

## Subclasses

Separate catalog at `/subclasses` — see `app/features/subclasses/README.md`.
`ClassResponse.subclasses` embeds brief rows, so every subclass write purges `classes`.
