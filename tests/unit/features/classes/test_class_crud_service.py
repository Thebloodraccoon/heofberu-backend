"""
Unit tests for ClassCrudService: create_class capability seeding, the
ClassFullResponse composition in get_by_id, and full-replace update_class.

The capability services (skills/features/throws/armor/weapons) and the
subclass crud service are faked, mirroring the background/race house
pattern, so the tests trace only the composition logic inside
``ClassCrudService`` and the CLASS_CACHE_NAMESPACES purge after writes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, ArmorProficiency, DiceType, WeaponProficiency
from app.core.exceptions import RecordNotFoundError
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.crud.service import ClassCrudService
from app.features.classes.schemas import ClassCreate, ClassFullResponse, ClassUpdate
from app.models.class_model import Class
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_class_row(**overrides) -> SimpleNamespace:
    base = {
        "id": 1,
        "name": "Fighter",
        "hit_dice": DiceType.D10,
        "skill_choice_count": 2,
        "spellcasting_ability": None,
        "description": "",
        "saving_throws": [],
        "armor_proficiencies": [],
        "weapon_proficiencies": [],
        "available_skills": [],
        "starting_items": [],
        "spell_slot_progression": [],
        "subclasses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_skill(**overrides) -> SimpleNamespace:
    base = {"id": 1, "key": "athletics", "name": "Athletics", "ability": AbilityScore.STR, "description": ""}
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeThrowsService:
    """Stands in for ClassThrowsService inside ClassCrudService."""

    def __init__(self, db):
        self.db = db
        self.set_calls = []

    async def set_saving_throws_for_class(self, character_class, abilities, *, commit=True):
        self.set_calls.append((character_class, abilities, commit))
        character_class.saving_throws = [SimpleNamespace(ability=ability) for ability in abilities]
        return character_class


class FakeArmorService:
    """Stands in for ClassArmorService inside ClassCrudService."""

    def __init__(self, db):
        self.db = db
        self.set_calls = []

    async def set_armor_proficiencies_for_class(self, character_class, armor_types, *, commit=True):
        self.set_calls.append((character_class, armor_types, commit))
        character_class.armor_proficiencies = [SimpleNamespace(armor_type=armor_type) for armor_type in armor_types]
        return character_class


class FakeWeaponService:
    """Stands in for ClassWeaponService inside ClassCrudService."""

    def __init__(self, db):
        self.db = db
        self.set_calls = []

    async def set_weapon_proficiencies_for_class(self, character_class, weapon_categories, *, commit=True):
        self.set_calls.append((character_class, weapon_categories, commit))
        character_class.weapon_proficiencies = [
            SimpleNamespace(weapon_category=weapon_category) for weapon_category in weapon_categories
        ]
        return character_class


class FakeSkillService:
    """Stands in for ClassSkillService inside ClassCrudService."""

    def __init__(self, db, resolved=None):
        self.db = db
        self.resolved = resolved
        self.resolve_calls = []
        self.set_calls = []

    async def resolve_skills(self, skill_ids):
        self.resolve_calls.append(skill_ids)
        return self.resolved

    async def set_skills_for_class(self, character_class, skills, *, commit=True):
        self.set_calls.append((character_class, skills, commit))
        character_class.available_skills = list(skills or [])


class FakeClassFeatureService:
    """Stands in for ClassFeatureService inside ClassCrudService."""

    def __init__(self, db, features=None):
        self.db = db
        self.features = features or []
        self.list_calls = []

    async def list_features(self, source_id):
        self.list_calls.append(source_id)
        return self.features


class FakeSubclassCrudService:
    """Stands in for SubclassCrudService inside ClassCrudService."""

    def __init__(self, db, subclasses=None):
        self.db = db
        self.subclasses = subclasses or []
        self.list_calls = []

    async def list_for_class(self, class_id):
        self.list_calls.append(class_id)
        return self.subclasses


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture
def invalidated(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.features.classes.crud.service.invalidate_class_cache", mock)
    return mock


def make_crud_service(existing_by_id=None, resolved_skills=None, features=None, subclasses=None):
    db = FakeAsyncSession()
    service = ClassCrudService(db)
    service.repository = FakeRepository(db, existing_by_id=existing_by_id, model=Class)
    service._skills = FakeSkillService(db, resolved=resolved_skills)
    service._throws = FakeThrowsService(db)
    service._armor = FakeArmorService(db)
    service._weapons = FakeWeaponService(db)
    service._features = FakeClassFeatureService(db, features=features)
    service.subclasses = FakeSubclassCrudService(db, subclasses=subclasses)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassCrudServiceCreate:
    async def test_create_class_seeds_capability_rows_inside_atomic(self, invalidated):
        skill = make_skill()
        service, db = make_crud_service(resolved_skills=[skill])
        data = ClassCreate(
            name="Fighter",
            hit_dice=DiceType.D10,
            spellcasting_ability=None,
            saving_throws=[AbilityScore.STR, AbilityScore.CON],
            armor_proficiencies=[ArmorProficiency.LIGHT, ArmorProficiency.SHIELD],
            weapon_proficiencies=[WeaponProficiency.SIMPLE, WeaponProficiency.MARTIAL],
            available_skills=[1],
        )

        result = await service.create_class(data)

        item = service.repository.created[0]
        assert result.id == 1
        assert item.name == "Fighter"
        assert service._skills.resolve_calls == [[1]]
        assert service._throws.set_calls == [(item, data.saving_throws, False)]
        assert service._armor.set_calls == [(item, data.armor_proficiencies, False)]
        assert service._weapons.set_calls == [(item, data.weapon_proficiencies, False)]
        assert service._skills.set_calls == [(item, [skill], False)]
        assert db.commits == 1
        assert invalidated.await_count == 1

    async def test_create_class_response_embeds_seeded_capability_rows(self, invalidated):
        service, _ = make_crud_service(
            resolved_skills=[make_skill()],
            existing_by_id={},
        )
        data = ClassCreate(
            name="Wizard",
            hit_dice=DiceType.D6,
            spellcasting_ability=AbilityScore.INT,
            saving_throws=[AbilityScore.INT, AbilityScore.WIS],
            armor_proficiencies=[ArmorProficiency.LIGHT],
            weapon_proficiencies=[WeaponProficiency.SIMPLE],
            available_skills=[1],
        )

        result = await service.create_class(data)

        assert [throw.ability for throw in result.saving_throws] == [AbilityScore.INT, AbilityScore.WIS]
        assert result.armor_proficiencies[0].armor_type == ArmorProficiency.LIGHT
        assert result.weapon_proficiencies[0].weapon_category == WeaponProficiency.SIMPLE
        assert result.available_skills[0].name == "Athletics"

    async def test_create_class_minimal_skips_capability_services(self, invalidated):
        service, db = make_crud_service()

        result = await service.create_class(ClassCreate(name="Fighter", hit_dice=DiceType.D10, spellcasting_ability=None))

        assert result.name == "Fighter"
        assert service._skills.resolve_calls == [None]
        assert service._throws.set_calls == []
        assert service._armor.set_calls == []
        assert service._weapons.set_calls == []
        assert service._skills.set_calls == []
        assert db.commits == 1

    async def test_create_class_rolls_back_when_persist_fails(self, invalidated):
        service, db = make_crud_service()

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_class(ClassCreate(name="Fighter", hit_dice=DiceType.D10, spellcasting_ability=None))

        assert db.rollbacks == 1
        assert invalidated.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassCrudServiceGetById:
    async def test_get_by_id_composes_full_response_with_features_and_subclasses(self, invalidated):
        feature = SimpleNamespace(id=3, name="Fighting Style", description="d", level=1)
        subclass = SimpleNamespace(id=2, class_id=1, name="Champion", description="")
        service, db = make_crud_service(existing_by_id={1: make_class_row()}, features=[feature], subclasses=[subclass])

        result = await service.get_by_id(1)

        assert isinstance(result, ClassFullResponse)
        assert result.id == 1
        assert result.features[0].id == 3
        assert result.subclasses[0].id == 2
        assert result.subclasses[0].name == "Champion"
        assert service._features.list_calls == [1]
        assert service.subclasses.list_calls == [1]
        assert db.commits == 0

    async def test_get_by_id_raises_when_class_missing(self, invalidated):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_by_id(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassCrudServiceUpdate:
    async def test_update_class_full_replaces_proficiencies(self, invalidated):
        class_row = make_class_row()
        service, _ = make_crud_service(existing_by_id={1: class_row})
        data = ClassUpdate(
            saving_throws=[AbilityScore.STR],
            armor_proficiencies=[ArmorProficiency.HEAVY],
            weapon_proficiencies=[WeaponProficiency.MARTIAL],
        )

        await service.update_class(1, data)

        assert service._throws.set_calls[0][1] == [AbilityScore.STR]
        assert service._armor.set_calls[0][1] == [ArmorProficiency.HEAVY]
        assert service._weapons.set_calls[0][1] == [WeaponProficiency.MARTIAL]
        assert all(call[2] is True for call in service._throws.set_calls)
        assert invalidated.await_count == 1

    async def test_update_class_scalar_only_patches_through_repository(self, invalidated):
        class_row = make_class_row()
        service, _ = make_crud_service(existing_by_id={1: class_row})

        result = await service.update_class(1, ClassUpdate(description="Martial archetype."))

        assert result.description == "Martial archetype."
        assert len(service.repository.updated) == 1
        assert service._throws.set_calls == []
        assert service._armor.set_calls == []
        assert service._weapons.set_calls == []
        assert invalidated.await_count == 1

    async def test_update_class_raises_when_class_missing(self, invalidated):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update_class(99, ClassUpdate(name="Knight"))


@pytest.mark.unit
class TestClassCacheNamespaces:
    def test_cache_namespaces_match_shared_constant(self):
        assert ClassCrudService.cache_namespaces == CLASS_CACHE_NAMESPACES
        assert set(CLASS_CACHE_NAMESPACES) == {"classes", "nested_features", "nested_items", "characters"}
