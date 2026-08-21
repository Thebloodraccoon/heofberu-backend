"""
Unit tests for the subrace subdomain services (crud / ability bonuses / features).

The services are exercised with recording fake repositories so the service
bodies (which integration tests through the HTTP layer do not trace) are
covered directly.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType
from app.core.exceptions import RecordNotFoundError
from app.features.races.ability_bonuses.schemas import AbilityBonusItem
from app.features.races.exceptions import SubraceNotFoundException
from app.features.races.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.races.subraces.crud.schemas import SubraceAbilityBonusesUpdate, SubraceCreate, SubraceUpdate
from app.features.races.subraces.crud.service import SubraceCrudService
from app.features.races.subraces.features.service import SubraceFeatureService
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate
from app.models.subrace_association_models import SubraceAbilityBonus
from app.models.subrace_model import Subrace
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_subrace(**overrides) -> Subrace:
    base = {
        "id": 1,
        "race_id": 1,
        "name": "High Elf",
        "description": "",
        "created_by_id": None,
        "ability_bonuses": [],
    }
    base.update(overrides)
    return Subrace(**base)


class FakeRaceRepository:
    """Race existence guard: exists_by_id returns a configured bool."""

    def __init__(self, db, exists: bool = True):
        self.db = db
        self._exists = exists

    async def exists_by_id(self, race_id: int) -> bool:
        return self._exists


class FakeSubraceRepository(FakeRepository):
    """Subrace repository stand-in with the capability methods the services need."""

    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Subrace)
        self.set_bonuses_calls = []
        self.list_calls = []

    async def list_for_race(self, race_id: int):
        self.list_calls.append(race_id)
        return [subrace for subrace in self._rows.values() if subrace.race_id == race_id]

    async def set_ability_bonuses(self, subrace: Subrace, bonuses: list[dict], *, commit: bool = True) -> Subrace:
        self.set_bonuses_calls.append((subrace, bonuses, commit))
        subrace.ability_bonuses = [
            SubraceAbilityBonus(subrace_id=subrace.id, ability=bonus["ability"], bonus=bonus["bonus"])
            for bonus in bonuses
        ]
        if commit:
            await self.db.commit()
        return subrace


class FakeNestedFeatureService:
    """Stands in for NestedFeatureService inside the subrace services."""

    def __init__(self, db):
        self.db = db
        self.invalidate_calls = 0
        self.created = []
        self.updated = []
        self.deleted = []

    async def list_for_source(self, source_type, source_id):
        return []

    async def create_features_for_source(self, source_type, source_id, items, created_by_id, *, commit=False):
        self.created.append((source_type, source_id, items, created_by_id, commit))
        return []

    async def create_feature_for_source(self, source_type, source_id, item, created_by_id, *, commit=False):
        self.created.append((source_type, source_id, item, created_by_id, commit))
        return SimpleNamespace(id=1, name=item.name, description=item.description, level=item.level)

    async def update_feature_for_source(self, source_type, source_id, feature_id, fields, *, commit=False):
        self.updated.append((source_type, source_id, feature_id, fields, commit))
        return SimpleNamespace(
            id=feature_id,
            name=fields.get("name", "Extra Attack"),
            description=fields.get("description", ""),
            level=fields.get("level"),
        )

    async def delete_feature_for_source(self, source_type, source_id, feature_id, *, commit=False):
        self.deleted.append((source_type, source_id, feature_id, commit))
        return None

    async def invalidate(self):
        self.invalidate_calls += 1


class FakeSubraceAbilityBonusService:
    """Stands in for SubraceAbilityBonusService inside SubraceCrudService."""

    def __init__(self, db):
        self.db = db
        self.calls = []

    async def set_ability_bonuses_for_subrace(self, subrace, bonuses, *, commit=True):
        self.calls.append((subrace, bonuses, commit))
        subrace.ability_bonuses = [
            SubraceAbilityBonus(subrace_id=subrace.id, ability=bonus["ability"], bonus=bonus["bonus"])
            for bonus in bonuses
        ]


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    """Stop cache invalidation from touching Redis."""
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture(autouse=True)
def no_subrace_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.races.subraces.crud.service.invalidate_subrace_cache", AsyncMock())
    monkeypatch.setattr("app.features.races.subraces.ability_bonuses.service.invalidate_subrace_cache", AsyncMock())
    monkeypatch.setattr("app.features.races.subraces.features.service.invalidate_subrace_cache", AsyncMock())


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.feature_sync.reconcile_characters_for_source", AsyncMock())


def make_crud_service(existing_by_id=None, race_exists=True):
    db = FakeAsyncSession()
    service = SubraceCrudService(db)
    service.repository = FakeSubraceRepository(db, existing_by_id=existing_by_id)
    service._features = FakeNestedFeatureService(db)
    service._ability_bonuses = FakeSubraceAbilityBonusService(db)
    service._race_repository = FakeRaceRepository(db, exists=race_exists)
    return service, db


def make_ability_bonus_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = SubraceAbilityBonusService(db)
    service.repository = FakeSubraceRepository(db, existing_by_id=existing_by_id)
    return service, db


def make_feature_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = SubraceFeatureService(db)
    service.repository = FakeSubraceRepository(db, existing_by_id=existing_by_id)
    service._features = FakeNestedFeatureService(db)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceCrudService:
    async def test_list_for_race_returns_serialized_subraces(self):
        existing = {1: make_subrace(id=1), 2: make_subrace(id=2, name="Wood Elf", race_id=1)}
        service, _ = make_crud_service(existing_by_id=existing)

        result = await service.list_for_race(1)

        assert [item.id for item in result] == [1, 2]
        assert result[0].name == "High Elf"
        assert service.repository.list_calls == [1]

    async def test_list_for_race_raises_when_race_missing(self):
        service, _ = make_crud_service(race_exists=False)

        with pytest.raises(RecordNotFoundError):
            await service.list_for_race(99)

    async def test_get_subrace_returns_serialized_row(self):
        subrace = make_subrace(ability_bonuses=[SubraceAbilityBonus(subrace_id=1, ability=AbilityScore.DEX, bonus=2)])
        service, _ = make_crud_service(existing_by_id={1: subrace})

        result = await service.get_subrace(1, 1)

        assert result.id == 1
        assert result.ability_bonuses[0].ability == AbilityScore.DEX
        assert result.ability_bonuses[0].bonus == 2

    async def test_get_subrace_raises_when_subrace_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(SubraceNotFoundException):
            await service.get_subrace(1, 99)

    async def test_get_subrace_raises_when_subrace_belongs_to_other_race(self):
        service, _ = make_crud_service(existing_by_id={1: make_subrace(id=1, race_id=1)})

        with pytest.raises(SubraceNotFoundException):
            await service.get_subrace(2, 1)

    async def test_create_subrace_without_nested_capabilities(self):
        service, db = make_crud_service(race_exists=True)

        result = await service.create_subrace(1, SubraceCreate(name="Drow", description="Underdark elf"))

        assert result.id == 1
        assert result.race_id == 1
        assert result.name == "Drow"
        assert db.commits == 1
        assert service.repository.created
        assert service._features.created == [(FeatureSourceType.SUBRACE, 1, None, None, False)]

    async def test_create_subrace_with_bonuses_and_features(self):
        service, db = make_crud_service(race_exists=True)
        data = SubraceCreate(
            name="High Elf",
            ability_bonuses=[AbilityBonusItem(ability=AbilityScore.DEX, bonus=2)],
            features=[NestedFeatureCreate(name="Keen Senses", description="", level=None)],
        )

        result = await service.create_subrace(1, data, created_by_id=7)

        assert result.ability_bonuses[0].ability == AbilityScore.DEX
        assert service._ability_bonuses.calls[0][1] == [{"ability": AbilityScore.DEX, "bonus": 2}]
        assert service._features.created[0] == (FeatureSourceType.SUBRACE, 1, data.features, 7, False)

    async def test_create_subrace_raises_when_race_missing(self):
        service, _ = make_crud_service(race_exists=False)

        with pytest.raises(RecordNotFoundError):
            await service.create_subrace(99, SubraceCreate(name="Drow"))

    async def test_create_subrace_rolls_back_when_persist_fails(self):
        service, db = make_crud_service(race_exists=True)

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_subrace(1, SubraceCreate(name="Drow"))

        assert db.rollbacks == 1

    async def test_update_subrace_delegates_to_base_update(self):
        subrace = make_subrace(id=1)
        service, db = make_crud_service(existing_by_id={1: subrace})

        result = await service.update_subrace(1, 1, SubraceUpdate(name="Wood Elf"))

        assert result.name == "Wood Elf"
        assert subrace.name == "Wood Elf"
        assert db.commits >= 1

    async def test_update_subrace_raises_when_subrace_belongs_to_other_race(self):
        service, _ = make_crud_service(existing_by_id={1: make_subrace(id=1, race_id=1)})

        with pytest.raises(SubraceNotFoundException):
            await service.update_subrace(2, 1, SubraceUpdate(name="Wood Elf"))

    async def test_delete_subrace_deletes_scoped_row(self):
        subrace = make_subrace(id=1)
        service, _ = make_crud_service(existing_by_id={1: subrace})

        result = await service.delete_subrace(1, 1)

        assert result is None
        assert service.repository.deleted == [subrace]

    async def test_delete_subrace_raises_when_subrace_belongs_to_other_race(self):
        service, _ = make_crud_service(existing_by_id={1: make_subrace(id=1, race_id=1)})

        with pytest.raises(SubraceNotFoundException):
            await service.delete_subrace(2, 1)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceAbilityBonusService:
    async def test_set_ability_bonuses_replaces_and_returns_subrace(self):
        subrace = make_subrace(id=1)
        service, db = make_ability_bonus_service(existing_by_id={1: subrace})
        data = SubraceAbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        result = await service.set_ability_bonuses(1, 1, data)

        assert result.ability_bonuses[0].ability == AbilityScore.INT
        assert result.ability_bonuses[0].bonus == 1
        assert service.repository.set_bonuses_calls[0][0] is subrace
        assert service.repository.set_bonuses_calls[0][1] == [{"ability": AbilityScore.INT, "bonus": 1}]
        assert service.repository.set_bonuses_calls[0][2] is True
        assert db.commits == 1

    async def test_set_ability_bonuses_raises_when_subrace_missing(self):
        service, _ = make_ability_bonus_service(existing_by_id={})
        data = SubraceAbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        with pytest.raises(SubraceNotFoundException):
            await service.set_ability_bonuses(1, 99, data)

    async def test_set_ability_bonuses_for_subrace_delegates_without_commit(self):
        subrace = make_subrace(id=1)
        service, db = make_ability_bonus_service()

        await service.set_ability_bonuses_for_subrace(
            subrace, [{"ability": AbilityScore.STR, "bonus": 1}], commit=False
        )

        assert service.repository.set_bonuses_calls == [(subrace, [{"ability": AbilityScore.STR, "bonus": 1}], False)]
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceFeatureService:
    async def test_list_features_delegates_to_nested_service(self):
        subrace = make_subrace(id=1)
        service, _ = make_feature_service(existing_by_id={1: subrace})

        result = await service.list_features(1, 1)

        assert result == []

    async def test_add_feature_creates_and_reconciles(self):
        subrace = make_subrace(id=1)
        service, db = make_feature_service(existing_by_id={1: subrace})
        data = NestedFeatureCreate(name="Fey Ancestry", description="d", level=None)

        result = await service.add_feature(1, 1, data, created_by_id=7)

        assert result.id == 1
        assert result.name == "Fey Ancestry"
        assert service._features.created == [(FeatureSourceType.SUBRACE, 1, data, 7, False)]
        assert service._features.invalidate_calls == 1
        assert db.commits == 1

    async def test_update_feature_updates_in_place(self):
        subrace = make_subrace(id=1)
        service, db = make_feature_service(existing_by_id={1: subrace})

        result = await service.update_feature(1, 1, 5, FeatureUpdate(name="Fey Ancestry"))

        assert result.id == 5
        assert service._features.updated == [(FeatureSourceType.SUBRACE, 1, 5, {"name": "Fey Ancestry"}, False)]
        assert db.commits == 1

    async def test_remove_feature_deletes_and_reconciles(self):
        subrace = make_subrace(id=1)
        service, db = make_feature_service(existing_by_id={1: subrace})

        result = await service.remove_feature(1, 1, 5)

        assert result is None
        assert service._features.deleted == [(FeatureSourceType.SUBRACE, 1, 5, False)]
        assert db.commits == 1

    async def test_feature_write_raises_when_subrace_belongs_to_other_race(self):
        subrace = make_subrace(id=1, race_id=1)
        service, _ = make_feature_service(existing_by_id={1: subrace})

        with pytest.raises(SubraceNotFoundException):
            await service.add_feature(2, 1, NestedFeatureCreate(name="x"))
