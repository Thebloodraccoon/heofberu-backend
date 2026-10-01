# Subclasses Catalog (`app/features/subclasses/`)

Standalone reference catalog for the `Subclass` entity, mounted at `/subclasses`
(the owning class is the subclass's `class_id`). A subclass belongs to exactly one
class; its features are `Feature` rows with `source_type=SUBCLASS`, written through
the central `/features` catalog.

## Layout

```
subclasses/
├── router.py        # assembles /subclasses
├── dependencies.py  # SubclassCrudDep, SubclassFeaturesDep, SubclassImageDep
├── cache.py         # SUBCLASS_CACHE_NAMESPACES, SUBCLASS_CRUD_CACHE_NAMESPACES (+spells), SUBCLASS_DELETE_CACHE_NAMESPACES
├── crud/            # repository (class-scoped uniqueness), schemas, service, router
├── features/        # read-only cached SUBCLASS-source feature list
└── image/           # catalog image upload/delete
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/subclasses?class_id=` | open | Brief rows (id/class_id/name/image_url) ordered by name, cached. Without `class_id` lists all; unknown `class_id` -> 404. Not paginated (a class has a handful of subclasses). |
| POST | `/subclasses` | GM | `name` 1-100, `class_id` > 0 (unknown -> 404), `description` <= 10000, `image_url` absolute http(s) <= 512. Name already used in that class -> 400. Responds with the full `SubclassResponse`. |
| GET | `/subclasses/{subclass_id}` | open | `SubclassResponse`: base fields + SUBCLASS-source `features`, cached. |
| PATCH | `/subclasses/{subclass_id}` | GM | `name`/`description` only; explicit `null` -> 422; `class_id` is immutable. Name clash is checked within the subclass's own class (a same-named subclass of another class is fine) -> 400. Responds with the full `SubclassResponse`. |
| DELETE | `/subclasses/{subclass_id}` | Founder | 409 while characters reference it. |
| GET | `/subclasses/{subclass_id}/features` | open | Cached feature list. |
| PUT/DELETE | `/subclasses/{subclass_id}/image` | GM | Multipart upload / clear. |

Subclasses carry no ability bonuses; those live on the subclass features' effects.

## Behaviour notes

- `SubclassRepository` overrides the `BaseRepository._uniqueness_scope` hook (`BaseRepository.update` takes
  `commit=False`): it supplies the existing row's
  `class_id`, so a PATCH that only sends `name` is checked against the right siblings.
- `get_by_id` serializes the eager-loaded `Subclass.features` (no second feature query) and
  is cached under `cache:classes:subclass:get_by_id:{id}` (own key: the `classes` namespace
  also holds `ClassCrudService.get_by_id`).
- Single-step writes let the repository commit; `delete` runs the in-use guard first.

## Cache

| Write | Purged |
| --- | --- |
| image | `classes` (subclass detail, listing, and the class reads that embed subclass rows) |
| create / update | `classes`, `spells` (spell listings embed subclass names) |
| delete | `classes`, `subclass_features`, `features`, `spells` (cascade) |

Subclass names are not part of cached character payloads, so `characters` is never purged.
Central feature writes purge `subclass_features` and `classes` themselves.
