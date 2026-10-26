"""Unit tests for the item schemas, the weapon rules, the core service's caching, the delete guard and filters."""

from decimal import Decimal

from pydantic import ValidationError
import pytest
from sqlalchemy import select

from app.constants import GearType, ItemKind
from app.core.exceptions import RecordInUseError
from app.features.items.armor.schemas import ArmorCreate, ArmorUpdate
from app.features.items.armor.service import check_armor
from app.features.items.cache import ITEM_CACHE_NAMESPACES, ITEM_DEPENDENT_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import GearCreate, ItemCoreUpdate, ItemResponse
from app.features.items.crud.service import ItemCrudService
from app.features.items.exceptions import InvalidItemDataError
from app.features.items.weapons.schemas import WeaponCreate, WeaponUpdate
from app.features.items.weapons.service import check_weapon
from app.models.items.item_model import Item, ItemArmorDetails, ItemWeaponDetails
from app.models.items.weapon_property_model import WeaponProperty
from tests.unit.fakes import FakeAsyncSession, FakeRepository


@pytest.fixture(autouse=True)
def purged(monkeypatch):
    calls: list[str] = []

    async def record(namespace):
        calls.append(namespace)

    monkeypatch.setattr("app.core.base.service.invalidate", record)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", record)
    return calls


def make_item(**overrides):
    base = {
        "id": 1,
        "name": "Rope",
        "kind": ItemKind.GEAR,
        "subtype": GearType.ADVENTURING_GEAR,
        "rarity": "NONE",
        "description": "",
        "requires_attunement": False,
    }
    base.update(overrides)
    return Item(**base)


class FakeItemRepository(FakeRepository):
    """``FakeRepository`` plus the item-specific calls of the service."""

    async def get_fresh(self, item_id):
        return await self.get_by_id(item_id)


def make_service(rows=()):
    db = FakeAsyncSession()
    service = ItemCrudService(db)
    service.repository = FakeItemRepository(db, existing_by_id={row.id: row for row in rows}, model=Item)
    return service


def prop(name, *, requires_range=False, requires_versatile_damage=False):
    return WeaponProperty(name=name, requires_range=requires_range, requires_versatile_damage=requires_versatile_damage)


@pytest.mark.unit
class TestItemSchemas:
    @pytest.mark.parametrize(
        ("schema", "extra"),
        [
            (GearCreate, {"weight": "-1"}),
            (GearCreate, {"weight": "10000"}),
            (GearCreate, {"weight": "1.234"}),
            (GearCreate, {"cost_gold": "100000000000"}),
            (GearCreate, {"magic_bonus": 11}),
            (GearCreate, {"name": "x" * 201}),
            (GearCreate, {"name": "  "}),
            (GearCreate, {"item_type": "WEAPON"}),
            (WeaponCreate, {"weapon": {"damage_dice_count": 0}}),
            (WeaponCreate, {"weapon": {"range_normal": 0}}),
            (WeaponCreate, {"weapon": {"armor_class_base": 12}}),
            (ArmorCreate, {"armor": {"armor_class_base": -1}}),
            (ArmorCreate, {"armor": {"strength_requirement": 31}}),
        ],
    )
    def test_create_rejects_out_of_range_or_foreign_values(self, schema, extra):
        with pytest.raises(ValidationError):
            schema(**{"name": "Odd", **extra})

    def test_create_accepts_column_limits(self):
        item = GearCreate(name="Big", weight=Decimal("9999.99"), cost_gold=Decimal("99999999.99"))

        assert (item.weight, item.subtype) == (Decimal("9999.99"), GearType.OTHER)

    @pytest.mark.parametrize("field", ["name", "subtype", "rarity", "requires_attunement", "description"])
    def test_core_update_rejects_null_for_required_fields(self, field):
        with pytest.raises(ValidationError):
            ItemCoreUpdate(**{field: None})

    def test_core_update_allows_clearing_nullable_fields(self):
        assert ItemCoreUpdate(weight=None).model_dump(exclude_unset=True) == {"weight": None}

    def test_detail_updates_reject_nulls_of_not_null_columns(self):
        with pytest.raises(ValidationError):
            ArmorUpdate(stealth_disadvantage=None)
        with pytest.raises(ValidationError):
            WeaponUpdate(property_ids=None)

    def test_weapon_properties_are_a_set(self):
        assert WeaponCreate(name="Spear", property_ids=[5, 9, 5]).property_ids == [5, 9]

    def test_response_carries_the_details_of_its_kind_only(self):
        item = make_item(kind=ItemKind.WEAPON, subtype=None)
        item.weapon = ItemWeaponDetails(damage_dice_count=1, damage_dice_type="D8")

        response = ItemResponse.model_validate(item)

        assert (response.weapon.damage_dice_count, response.armor, response.tool) == (1, None, None)

    def test_read_through_properties_are_none_on_another_kind(self):
        armor = make_item(kind=ItemKind.ARMOR, subtype=None)
        armor.armor = ItemArmorDetails(armor_category="SHIELD", armor_class_base=2)
        rope = make_item()

        assert (armor.armor_category, armor.armor_class_base, armor.weapon_category) == ("SHIELD", 2, None)
        assert (rope.armor_category, rope.tool_category) == (None, None)

    def test_namespaces_include_feature_caches_that_render_item_names(self):
        assert ITEM_CACHE_NAMESPACES[0] == "items"
        assert {"nested_items", "classes", "races", "backgrounds", "features", "feats", "race_features"} <= set(
            ITEM_DEPENDENT_CACHE_NAMESPACES
        )


@pytest.mark.unit
class TestCheckWeapon:
    def test_thrown_weapon_needs_a_range(self):
        with pytest.raises(InvalidItemDataError, match="range_normal"):
            check_weapon({}, [prop("Метательное", requires_range=True)], check_properties=True)

    def test_versatile_weapon_needs_its_two_handed_damage(self):
        with pytest.raises(InvalidItemDataError, match="versatile"):
            check_weapon({}, [prop("Универсальное", requires_versatile_damage=True)], check_properties=True)

    def test_half_set_versatile_damage_is_rejected(self):
        with pytest.raises(InvalidItemDataError):
            check_weapon({"versatile_dice_count": 1}, [], check_properties=False)

    @pytest.mark.parametrize("ranges", [{"range_long": 60}, {"range_normal": 60, "range_long": 20}])
    def test_long_range_needs_a_shorter_normal_one(self, ranges):
        with pytest.raises(InvalidItemDataError, match="range_long"):
            check_weapon(ranges, [], check_properties=False)

    def test_property_requirements_skipped_when_not_checked(self):
        check_weapon({}, [prop("Метательное", requires_range=True)], check_properties=False)

    def test_complete_weapon_passes(self):
        check_weapon(
            {"range_normal": 20, "range_long": 60, "versatile_dice_count": 1, "versatile_dice_type": "D8"},
            [prop("Метательное", requires_range=True), prop("Универсальное", requires_versatile_damage=True)],
            check_properties=True,
        )


@pytest.mark.unit
class TestCheckArmor:
    @pytest.mark.parametrize("category", ["LIGHT", "MEDIUM", "HEAVY", "SHIELD"])
    def test_a_categorised_armor_needs_its_base(self, category):
        with pytest.raises(InvalidItemDataError, match="armor_class_base"):
            check_armor({"armor_category": category, "armor_class_base": None})

    def test_complete_or_uncategorised_armor_passes(self):
        check_armor({"armor_category": "SHIELD", "armor_class_base": 2})
        check_armor({"armor_category": None, "armor_class_base": None})


@pytest.mark.unit
@pytest.mark.asyncio
class TestItemCaching:
    async def test_create_purges_only_the_item_listing(self, purged):
        service = make_service()

        created = await service.create(GearCreate(name="Rope"))

        assert purged == ["items"]
        assert (created.kind, created.subtype) == (ItemKind.GEAR, GearType.OTHER)

    async def test_update_purges_every_dependent_namespace(self, purged):
        service = make_service([make_item()])

        await service.update(1, ItemCoreUpdate(name="Silk Rope"))

        assert set(purged) == set(ITEM_CACHE_NAMESPACES)

    async def test_subtype_of_a_non_gear_item_is_rejected(self, purged):
        service = make_service([make_item(kind=ItemKind.WEAPON, subtype=None)])

        with pytest.raises(InvalidItemDataError, match="GEAR"):
            await service.update(1, ItemCoreUpdate(subtype=GearType.RING))

        assert purged == []

    async def test_delete_purges_only_the_item_listing(self, purged):
        service = make_service([make_item()])

        await service.delete(1)

        assert purged == ["items"]


class RecordingSession(FakeAsyncSession):
    """Answers each ``exists_referencing`` query in turn and remembers which tables were asked about."""

    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)
        self.statements = []

    async def scalar(self, stmt):
        self.statements.append(str(stmt))
        return self.answers.pop(0) if self.answers else None


@pytest.mark.unit
@pytest.mark.asyncio
class TestItemRepositoryGuard:
    async def test_guard_covers_every_table_referencing_the_item(self):
        session = RecordingSession([None] * 8)

        assert await ItemRepository(session).is_in_use(1) is False

        joined = " ".join(session.statements)
        for table in (
            "character_items",
            "character_proficiencies",
            "character_feature_choices",
            "feature_weapon_proficiency_effects",
            "feature_tool_proficiency_effects",
            "source_items",
            "source_item_choice_options",
        ):
            assert table in joined

    async def test_cascading_character_proficiency_blocks_the_delete(self):
        session = RecordingSession([None, 1])

        assert await ItemRepository(session).is_in_use(1) is True
        assert "character_proficiencies" in session.statements[1]

    async def test_delete_locks_the_item_row_first(self):
        session = RecordingSession([None, 1, 1])
        repository = ItemRepository(session)

        with pytest.raises(RecordInUseError):
            await repository.delete(make_item())

        assert "FOR UPDATE" in str(session.executes[0])
        assert session.deleted == []


@pytest.mark.unit
class TestItemFilters:
    def compiled(self, filters):
        return str(ItemRepository(FakeAsyncSession())._apply_filters(select(Item), filters))

    def test_detail_categories_filter_through_their_detail_table(self):
        sql = self.compiled({"weapon_category": ["SIMPLE"], "armor_category": ["SHIELD"]})

        assert "item_weapon_details" in sql and "item_armor_details" in sql

    def test_magic_filters_on_rarity_and_core_columns_stay_exact_match(self):
        sql = self.compiled({"magic": True, "kind": ["WEAPON"]})

        assert "items.rarity !=" in sql and "items.kind IN" in sql

    def test_unset_filters_add_nothing(self):
        assert "WHERE" not in self.compiled({"weapon_category": None, "magic": None, "property_id": []})
