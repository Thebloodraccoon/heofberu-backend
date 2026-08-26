# Items Catalog

Reference catalog for the `Item` entity — weapons, armor, and general equipment with type/rarity/weight/cost plus weapon-specific (damage dice, properties) and armor-specific (AC base, dex bonus, strength requirement...) fields. This catalog also OWNS the starting-equipment set: the `source_items` join rows that attach items to classes and backgrounds as their granted starting equipment (exposed to clients through the parents' `/items` capabilities backed by `app/features/shared/items/`; character creation collects them in bulk via `ItemRepository.get_source_items_for_sources`).

## Layout

- `crud/` — the single capability: `repository.py` (`ItemRepository`), `service.py` (`ItemCrudService`), `schemas.py`, `router.py` (bare router).
- `../items/cache.py` — cache namespaces + invalidation helper.
- `../items/dependencies.py` — `ItemCrudDep` service dependency.
- `../items/exceptions.py` — `ItemNotFoundException` (404).
- `../items/router.py` — assembles the surface under `/items`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/items` | open | Paginated list (`Page[ItemGetAllResponse]`: id/name/type/rarity/cost only). Filters: repeatable `item_type`, repeatable `rarity`, `search` on name. |
| GET | `/items/{item_id}` | open | Full `ItemResponse` including weapon/armor detail fields. |
| POST | `/items` | GM | 409 on duplicate `name`. |
| PATCH | `/items/{item_id}` | GM | Partial update; duplicate `name` → 409. |
| DELETE | `/items/{item_id}` | Founder | Blocked with 409 while referenced anywhere (see below). |

## Service composition

Simple catalog: one capability. `ItemCrudService` extends `CachedService[...]` over `ItemRepository`:

- Uniqueness on `name` before create/update (`unique_fields=["name"]`) → 409.
- `create_item` is the only custom write (uniqueness check + explicit `invalidate_item_cache()`); reads and delete are inherited unchanged from `CachedService`.
- Delete guard (`check_in_use_on_delete=True` → `ItemRepository.is_in_use`) blocks removal while any `character_items` row (inventory) or `source_items` row (class/background starting equipment) references the item — both FKs are `ON DELETE RESTRICT`.
- `SOURCE_ITEM_FK_BY_SOURCE_TYPE` at the repository maps CLASS/BACKGROUND source types to their `source_items` FK column; OTHER/feat-style sources have none.

## Cache

`ITEM_CACHE_NAMESPACES = ("items", "nested_items", "classes", "backgrounds")`, purged by `invalidate_item_cache()` after every committed write: per-source starting-equipment listings are cached under `nested_items` and embed `ItemBriefResponse` rows joined from this table, and the class/background FullResponses embed item briefs too. The parent catalogs declare `"items"` in their own `cache_namespaces` for the reverse direction.
