"""Unit tests for the item schemas, delete guard and cache namespaces."""

from decimal import Decimal

from pydantic import ValidationError
import pytest

from app.core.exceptions import RecordInUseError
from app.features.items.cache import ITEM_CACHE_NAMESPACES, ITEM_DEPENDENT_CACHE_NAMESPACES
from app.features.items.crud.repository import ItemRepository
from app.features.items.crud.schemas import ItemCreate, ItemUpdate
from app.features.items.crud.service import ItemCrudService
from app.models.items.item_model import Item
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
        "name": "Longsword",
        "item_type": "WEAPON",
        "rarity": "NONE",
        "description": "",
        "requires_attunement": False,
        "armor_class_dex_bonus": True,
        "stealth_disadvantage": False,
    }
    base.update(overrides)
    return Item(**base)


def make_service(rows=()):
    db = FakeAsyncSession()
    service = ItemCrudService(db)
    service.repository = FakeRepository(db, existing_by_id={row.id: row for row in rows}, model=Item)
    return service


@pytest.mark.unit
class TestItemSchemas:
    @pytest.mark.parametrize(
        "extra",
        [
            {"weight": "-1"},
            {"weight": "10000"},
            {"weight": "1.234"},
            {"cost_gold": "100000000000"},
            {"damage_dice_count": 0},
            {"armor_class_base": -1},
            {"strength_requirement": 31},
            {"weapon_properties": "x" * 301},
            {"name": "x" * 201},
            {"name": "  "},
        ],
    )
    def test_create_rejects_out_of_range_values(self, extra):
        with pytest.raises(ValidationError):
            ItemCreate(**{"name": "Odd", "item_type": "WEAPON", **extra})

    def test_create_accepts_column_limits(self):
        item = ItemCreate(name="Big", item_type="ARMOR", weight=Decimal("9999.99"), cost_gold=Decimal("99999999.99"))

        assert item.weight == Decimal("9999.99")

    @pytest.mark.parametrize("field", ["name", "item_type", "rarity", "requires_attunement", "description"])
    def test_update_rejects_null_for_required_fields(self, field):
        with pytest.raises(ValidationError):
            ItemUpdate(**{field: None})

    def test_update_allows_clearing_nullable_fields(self):
        assert ItemUpdate(weight=None).model_dump(exclude_unset=True) == {"weight": None}

    def test_namespaces_include_feature_caches_that_render_item_names(self):
        assert ITEM_CACHE_NAMESPACES[0] == "items"
        assert {"nested_items", "classes", "races", "backgrounds", "features", "feats", "race_features"} <= set(
            ITEM_DEPENDENT_CACHE_NAMESPACES
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestItemCaching:
    async def test_create_purges_only_the_item_listing(self, purged):
        service = make_service()

        await service.create(ItemCreate(name="Dagger", item_type="WEAPON"))

        assert purged == ["items"]

    async def test_update_purges_every_dependent_namespace(self, purged):
        service = make_service([make_item()])

        await service.update(1, ItemUpdate(name="Greatsword"))

        assert set(purged) == set(ITEM_CACHE_NAMESPACES)

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
        session = RecordingSession([None, None, None, None, None])

        assert await ItemRepository(session).is_in_use(1) is False

        joined = " ".join(session.statements)
        for table in (
            "character_items",
            "character_proficiencies",
            "feature_weapon_proficiency_effects",
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
