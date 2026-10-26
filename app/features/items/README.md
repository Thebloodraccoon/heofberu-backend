# Items Catalog

Reference catalog for the `Item` entity. This catalog also OWNS the starting-equipment set: the `source_items` join rows that attach items to classes and backgrounds as their granted starting equipment (exposed to clients through the parents' `/items` capabilities backed by `app/features/shared/items/`; character creation collects them in bulk via `ItemRepository.get_source_items_for_sources`).

## Model: a shared core + one detail record per kind

| Table | Holds |
| ----- | ----- |
| `items` | the core every item has: the one `id` every FK points at (inventory, starting equipment, proficiency effects, tool picks, item effects), `kind`, `subtype`, `rarity`, `requires_attunement`, `weight`, `cost_gold`, `magic_bonus`, `description` |
| `item_weapon_details` | `WEAPON`: `weapon_category`, `attack_type`, `damage_dice_*`, `damage_type`, `range_normal`/`range_long` (ft), `versatile_dice_*` (two-handed damage) |
| `item_armor_details` | `ARMOR`: `armor_category` (LIGHT/MEDIUM/HEAVY/**SHIELD**), `armor_class_base` (a shield's bonus for SHIELD), `armor_class_max_dex_bonus` (MEDIUM's DEX cap, 2 when unset), `strength_requirement`, `stealth_disadvantage` |
| `item_tool_details` | `TOOL`: `tool_category` (`ToolCategory`) |
| `item_weapon_properties` | a weapon's properties (the `weapon_properties` dictionary) |

- `kind` (`ItemKind`: `WEAPON` / `ARMOR` / `TOOL` / `GEAR`) is fixed at creation and decides which detail record the item has; `GEAR` has none, only its `subtype` (`GearType`: potion, scroll, wondrous item, ring, rod, staff, wand, adventuring gear, ammunition, treasure, other).
- **Magic is not a kind**: any item can be magical — `rarity`, `requires_attunement`, `magic_bonus` (+N of armor/shields to AC, weapons to attack and damage) and the speed/AC effects it gives while equipped. "Magic items" = `GET /items?magic=true`.
- The detail records load with the item (`lazy="joined"`; the `GET /items` listing selects their columns through outer joins, `ItemRepository.get_listing`); `Item` exposes read-through properties (`armor_category`, `armor_class_base`, `armor_class_max_dex_bonus`, `strength_requirement`, `weapon_category`, `tool_category`) for the rules that read them (combat stats, tool picks, starting-equipment filters) — `None` on an item of another kind.
- Next step (planned): magic variants of a base item (`base_item_id` — "Longsword +1" inherits the longsword's stats).

## Layout

- `crud/` — the core: `repository.py` (`ItemRepository`: filters through the detail tables, `item_detail_loads`, delete guard, the flush-only writes of detail records and item effects, the item-row `lock`), `service.py` (`ItemCrudService`: cached reads, `GEAR` create, core PATCH, delete), `kinds.py` (`KindItemService`: the shared create / detail-PATCH flow of a kind — core + detail record in one transaction, kind check), `schemas.py` (`ItemResponse`, detail views, core writes), `router.py`.
- `weapons/` — `WeaponService` (`check_weapon`: range order, two-handed damage both-or-none, properties' required fields — checked when the request touches properties/range/two-handed damage), `POST /items/weapons`, `PATCH /items/{id}/weapon`.
- `armor/` — `ArmorService` (`check_armor`: an `armor_category` (LIGHT/MEDIUM/HEAVY/SHIELD) needs `armor_class_base`, 422), `POST /items/armor`, `PATCH /items/{id}/armor`.
- `tools/` — `ToolService`, `POST /items/tools`, `PATCH /items/{id}/tool`.
- `properties/` — the weapon-property dictionary (`WeaponPropertyService`; writes purge only `items`).
- `effects/` — `ItemEffectsService`: the item's `speed` / `armor_class` effect rows (`item_id` parent), applied to a character while the item is equipped (and attuned when it `requires_attunement`) by `characters/combat`.
- `cache.py`, `dependencies.py` (`ItemCrudDep`, `WeaponServiceDep`, `ArmorServiceDep`, `ToolServiceDep`, `WeaponPropertyDep`, `ItemEffectsDep`), `exceptions.py` (`ItemNotFoundException` 404, `InvalidItemDataError` 422, `WrongItemKindError` 409), `router.py`.
- Documented catalog edge: `crud/schemas.py` and `effects/` import `app.features.features.effects.schemas` (the effect item/group schemas).

## Endpoints

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/items` | open | `Page[ItemGetAllResponse]` (id/name/kind/subtype/rarity/cost + the kind's category), by name. Repeatable filters `id` (any of), `kind`, `subtype`, `rarity`, `weapon_category`, `armor_category`, `tool_category`, `property_id` (weapons having ALL); `magic`; `search`. |
| GET | `/items/{item_id}` | open | `ItemResponse`: core + `weapon`/`armor`/`tool` (the others `null`) + `properties` + `effects`. |
| POST | `/items` | GM | A `GEAR` item (`subtype`, default OTHER). |
| POST | `/items/weapons` · `/items/armor` · `/items/tools` | GM | Core + `weapon` / `armor` / `tool` stats; weapons also `property_ids` (400 unknown, 422 rules). |
| PATCH | `/items/{item_id}` | GM | Core only; `subtype` on a non-GEAR item → 422; duplicate name → 409. |
| PATCH | `/items/{item_id}/weapon` · `/armor` · `/tool` | GM | The kind's stats, only the fields sent; another kind → 409. Weapon `property_ids` replaces the list. |
| DELETE | `/items/{item_id}` | Founder | 409 while referenced anywhere (see below). |
| GET / POST | `/items/properties` | open / GM | The property dictionary. |
| PATCH / DELETE | `/items/properties/{id}` | GM | Delete → 409 while a weapon has it. |
| GET / POST | `/items/{item_id}/effects` | open / GM | `static_groups` of `speed` / `armor_class` effects only. |
| DELETE | `/items/{item_id}/effects/{effect_type}/{effect_id}` | GM | |

## Service composition

- Uniqueness on `name` (`unique_fields=["name"]`).
- Delete guard (`ItemRepository.is_in_use`) blocks removal while any of these reference the item: `character_items`, `character_proficiencies` (**cascading** FK, checked in code), `character_feature_choices.picked_item_id`, `feature_weapon_proficiency_effects`, `feature_armor_proficiency_effects`, `feature_tool_proficiency_effects`, `source_items`, `source_item_choice_options`. `delete` locks the item row first. The detail record, property links and the item's own effects cascade away with it.
- A starting-equipment choice option is a concrete `item_id` OR a filter (`kind`/`weapon_category`/`armor_category`/`tool_category`, `ck_choice_option_item_or_filter`; at most one category, which implies its kind — `ChoiceOptionEntry` 422s `kind=ARMOR` + `weapon_category`); creation resolves a filter option to the item named in `item_choice_picks` (`characters/crud/rules.py:picked_items`).

## Cache

`cache.py`: `ITEM_OWN_CACHE_NAMESPACES = ("items",)` and `ITEM_DEPENDENT_CACHE_NAMESPACES` (`nested_items`, classes, races, backgrounds, features, feats and every `*_features` list; derived from `CACHE_DEPENDENTS["items"]` in `app/core/cache/namespaces.py`).

- a **core update** (it may rename the item) purges all of them (`ITEM_CACHE_NAMESPACES`);
- **create** (any kind), **delete**, a kind's **detail PATCH**, **property-dictionary** writes and **item-effect** writes purge only `items` — the dependents embed just an item's id/name/kind.

`ItemEffectsService.add_effects` locks the item row before its duplicate check.

All purges run after the commit. The character combat stats are computed per request and the cached character response embeds no items, so no character purge is needed (equip/unequip purges nothing).
