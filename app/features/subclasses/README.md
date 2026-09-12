# Subclasses Catalog (`app/features/subclasses/`)

Standalone reference catalog for the `Subclass` entity, split out of the
classes domain and mounted at the top-level `/subclasses` prefix (the parent
class is identified by `class_id`). A subclass is owned by exactly one class;
its features are `Feature` rows with `source_type=SUBCLASS`.

## Layout

```
subclasses/
├── router.py            # assembles /subclasses (one include_router per capability)
├── dependencies.py      # SubclassCrudDep, SubclassFeaturesDep, SubclassImageDep
├── cache.py             # SUBCLASS_CACHE_NAMESPACES + invalidate_subclass_cache()
├── crud/                # subclass CRUD, optional class_id listing filter, atomic nested creation
├── features/            # read-only cached SUBCLASS-source feature list
└── image/               # catalog image upload/delete
```

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/subclasses?class_id=` | open | Light `SubclassGetAllResponse` rows (id/class_id/name/image_url); `class_id` is an optional filter — omit it to list all subclasses, pass it to scope to one class. Missing class → 404. |
| POST | `/subclasses` | GM | Body is base fields plus `class_id` (the owning class) only — this catalog does NOT embed features at create; attach them afterwards via `POST /features` with `source_type=SUBCLASS`/`subclass_id`. Duplicate name within the class → 409. |
| GET | `/subclasses/{subclass_id}` | open | Full `SubclassResponse` — base fields + SUBCLASS-source `features`; cached as one unit. |
| PATCH | `/subclasses/{subclass_id}` | GM | Base fields only (`class_id` is immutable, not in the Update schema); 409 on name clash within the class. |
| DELETE | `/subclasses/{subclass_id}` | Founder | Removes the row; blocked with 409 while any character still references the subclass. |
| GET | `/subclasses/{subclass_id}/features` | open | Cached SUBCLASS-source feature list (read-only). |
| PUT | `/subclasses/{subclass_id}/image` | GM | Multipart upload/replace (JPEG/PNG/WebP/GIF, max 5 MB) → `{"image_url"}`. |
| DELETE | `/subclasses/{subclass_id}/image` | GM | Clears `image_url` and removes the stored object. |

Unlike subraces, subclasses carry **no ability bonuses** — that data is defined
on the subclass feature's effects through the feature cart (e.g. an
`AbilityEffectItem` choice group). `PUT .../subclasses/{subclass_id}/features`
does NOT exist; subclass feature writes go through the central `/features`
catalog with `source_type=SUBCLASS`.

## Service Composition

`SubclassCrudService` extends `BaseService` (not `CachedService` — the listing
is optionally class-scoped and only `get_by_id` is cached, via `@use_cache`)
and composes explicitly in `__init__`:

- `self._features = FeatureCrudService(db)` — `get_by_id` folds the subclass's
  own SUBCLASS-source `features` into `SubclassResponse` (cached under
  `classes:subclass:get_by_id`). Note the schema's create docstring still says
  features are created atomically, but there is no `features` field on
  `SubclassCreate` — subclass features are written through the central
  `/features` catalog.
- `self._class_repository = ClassRepository(db)` — `list_for_class` /
  `_ensure_class_exists`, translating a missing class into
  `RecordNotFoundError` (404).

Name uniqueness is **class-scoped** (`SubclassRepository._check_uniqueness`
filters on `class_id`), and deletion runs the generic `check_in_use_on_delete`
guard (`is_in_use` → any `Character` row pointing at the subclass).

## Cache Invalidation

`cache.py` owns `invalidate_subclass_cache()`, purging `SUBCLASS_CACHE_NAMESPACES
= ("classes", "subclass_features", "features")` after every committed write.
`classes` is included because `ClassResponse`/`ClassGetAllResponse` embed the
class's subclasses. `subclass_features` is additionally purged directly by the
central `FeatureCrudService._purge_feature_cache` whenever a feature write
touches a SUBCLASS-source feature. (Subclass feature grants reach characters
in the same transaction as the class-feature sync; the subclass name itself
appears in character payloads derived live, so subclass writes also trigger the
`features`/`classes` purge path above.)