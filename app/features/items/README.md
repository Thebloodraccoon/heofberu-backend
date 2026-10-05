# Items Catalog

Reference catalog for the `Item` entity — weapons, armor, and general equipment with type/rarity/weight/cost plus weapon-specific (damage dice, properties) and armor-specific (AC base, dex bonus, strength requirement...) fields. This catalog also OWNS the starting-equipment set: the `source_items` join rows that attach items to classes and backgrounds as their granted starting equipment (exposed to clients through the parents' `/items` capabilities backed by `app/features/shared/items/`; character creation collects them in bulk via `ItemRepository.get_source_items_for_sources`).

## Layout

- `crud/` — the single capability: `repository.py` (`ItemRepository`), `service.py` (`ItemCrudService`), `schemas.py`, `router.py` (bare router).
- `cache.py` — cache namespace tuples.
- `dependencies.py` — `ItemCrudDep` service dependency.
- `exceptions.py` — `ItemNotFoundException` (404), raised by the characters module.
- `router.py` — assembles the surface under `/items`.

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/items` | open | Paginated list (`Page[ItemGetAllResponse]`: id/name/type/rarity/cost only), ordered by name. Filters: repeatable `item_type`, repeatable `rarity`, `search` on name (max 100 chars). |
| GET | `/items/{item_id}` | open | Full `ItemResponse` including weapon/armor detail fields. |
| POST | `/items` | GM | Duplicate `name` → 400. |
| PATCH | `/items/{item_id}` | GM | Partial update; duplicate `name` → 409; explicit `null` for a required field → 422 (nullable weapon/armor/price fields can be cleared with `null`). |
| DELETE | `/items/{item_id}` | Founder | Blocked with 409 while referenced anywhere (see below). |

Duplicates answer **400** (`RecordAlreadyExistsError`, platform-wide), not 409. Input bounds follow the columns: `name` 1..200 (trimmed), `weight` `Numeric(6,2)`, `cost_gold` `Numeric(10,2)` (both >= 0), `weapon_properties` <= 300, small ranges for dice count / AC / strength requirement. The item type is not cross-checked against the weapon/armor fields (GM data entry stays free-form).

## Service composition

`ItemCrudService` extends `CachedService[...]` over `ItemRepository`; create goes through the inherited `create` (overridden only for the narrower cache purge).

- Uniqueness on `name` (`unique_fields=["name"]`).
- Delete guard (`ItemRepository.is_in_use`) blocks removal while any of these reference the item: `character_items` (inventory, RESTRICT), `character_proficiencies` (weapon proficiency by item, **cascading** FK, so it must be checked in code), `feature_weapon_proficiency_effects` (RESTRICT), `source_items` (class/background starting equipment) and `source_item_choice_options`. `delete` locks the item row first (`SELECT ... FOR UPDATE`) so a concurrent reference can't be cascaded away between the guard and the DELETE.
- `SOURCE_ITEM_FK_BY_SOURCE_TYPE` at the repository maps CLASS/BACKGROUND source types to their `source_items` FK column.

## Cache

`cache.py`: `ITEM_OWN_CACHE_NAMESPACES = ("items",)` and `ITEM_DEPENDENT_CACHE_NAMESPACES` (`nested_items`, classes, races, backgrounds, features, feats and every `*_features` list; derived from `CACHE_DEPENDENTS["items"]` in `app/core/cache/namespaces.py`). Per-source equipment listings (`nested_items`) and class/background details embed item briefs, and `effects_summary` renders weapon-proficiency item names, so:

- **update** purges all of them (`ITEM_CACHE_NAMESPACES`, the service's `cache_namespaces`);
- **create** and **delete** purge only `items` (a new item isn't referenced yet; an item can only be deleted once nothing references it).

All purges run after the commit. The parent catalogs declare `"items"` in their own `cache_namespaces` for the reverse direction.
