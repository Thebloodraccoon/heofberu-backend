"""
Unit tests for the race crud / ability-bonus / skill services and repositories.

Covers the service bodies that integration tests through the HTTP layer do not
trace: ``create_race`` with nested capabilities, the public ability-bonus
replacement, the shared ``SkillsManagerMixin.set_skills`` path, and the
repository ``get_subrace``/``set_ability_bonuses``/``set_skills`` methods.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType, RaceSize
from app.core.exceptions import RecordNotFoundError
from app.features.races.ability_bonuses.schemas import AbilityBonusItem
from app.features.races.ability_bonuses.service import RaceAbilityBonusService
from app.features.races.crud.repository import RaceRepository
from app.features.races.crud.service import RaceCrudService
from app.features.races.schemas import AbilityBonusesUpdate, RaceCreate, SkillsUpdate
from app.features.races.skills.repository import RaceSkillsRepository
from app.features.races.skills.service import RaceSkillService
from app.features.shared.features.schemas import NestedFeatureCreate
from app.models.race_association_models import RaceAbilityBonus
from app.models.race_model import Race
from app.models.skill_model import Skill
from tests.unit.fakes import FakeAsyncSession, FakeRepository, FakeResult


def make_race(**overrides) -> Race:
    base = {
        "id": 1,
        "name": "Elf",
        "size": RaceSize.MEDIUM,
        "speed": 30,
        "description": "",
        "ability_bonuses": [],
        "granted_skills": [],
        "subraces": [],
    }
    base.update(overrides)
    return Race(**base)


def make_skill(**overrides) -> Skill:
    base = {
        "id": 1,
        "key": "perception",
        "name": "Perception",
        "ability": AbilityScore.WIS,
        "description": "",
    }
    base.update(overrides)
    return Skill(**base)


def make_subrace(**overrides):
    base = {
        "id": 1,
        "race_id": 1,
        "name": "High Elf",
        "description": "",
        "ability_bonuses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeRaceRepository(FakeRepository):
    """Race repository stand-in with the capability methods the services need."""

    def __init__(self, db, existing_by_id=None, skills=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Race)
        self.skills = skills or {}
        self.set_ability_bonuses_calls = []
        self.set_skills_calls = []
        self.get_skills_calls = []

    async def create(self, payload, *, commit=True):
        row = Race(
            id=self._next_id,
            name=payload["name"],
            size=payload["size"],
            speed=payload["speed"],
            description=payload.get("description", ""),
            ability_bonuses=[],
            granted_skills=[],
            subraces=[],
        )
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        if commit:
            await self.db.commit()
        return row

    async def set_ability_bonuses(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> Race:
        self.set_ability_bonuses_calls.append((race, bonuses, commit))
        race.ability_bonuses = [
            RaceAbilityBonus(race_id=race.id, ability=bonus["ability"], bonus=bonus["bonus"]) for bonus in bonuses
        ]
        if commit:
            await self.db.commit()
        return race

    async def set_skills(self, race: Race, skills: list[Skill] | None, *, commit: bool = True) -> Race:
        self.set_skills_calls.append((race, skills, commit))
        race.granted_skills = list(skills or [])
        if commit:
            await self.db.commit()
        return race

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        self.get_skills_calls.append(skill_ids)
        return [self.skills[skill_id] for skill_id in skill_ids if skill_id in self.skills]


class FakeRaceSkillsService:
    """Stands in for RaceSkillService inside RaceCrudService."""

    def __init__(self, db, resolved=None):
        self.db = db
        self.resolved = resolved
        self.resolve_calls = []
        self.set_calls = []

    async def resolve_skills(self, skill_ids):
        self.resolve_calls.append(skill_ids)
        return self.resolved

    async def set_skills_for_race(self, race, skills, *, commit=True):
        self.set_calls.append((race, skills, commit))
        race.granted_skills = list(skills or [])


class FakeRaceAbilityBonusService:
    """Stands in for RaceAbilityBonusService inside RaceCrudService."""

    def __init__(self, db):
        self.db = db
        self.calls = []

    async def set_ability_bonuses_for_race(self, race, bonuses, *, commit=True):
        self.calls.append((race, bonuses, commit))
        race.ability_bonuses = [
            RaceAbilityBonus(race_id=race.id, ability=bonus["ability"], bonus=bonus["bonus"]) for bonus in bonuses
        ]


class FakeNestedFeatureService:
    """Stands in for NestedFeatureService inside RaceCrudService."""

    def __init__(self, db):
        self.db = db
        self.created = []

    async def create_features_for_source(self, source_type, source_id, items, *, commit=False):
        self.created.append((source_type, source_id, items, commit))


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    """Stop generic cache invalidation from touching Redis."""
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture(autouse=True)
def no_race_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.races.crud.service.invalidate_race_cache", AsyncMock())
    monkeypatch.setattr("app.features.races.ability_bonuses.service.invalidate_race_cache", AsyncMock())


def make_crud_service(existing_by_id=None, resolved_skills=None):
    db = FakeAsyncSession()
    service = RaceCrudService(db)
    service.repository = FakeRaceRepository(db, existing_by_id=existing_by_id)
    service._skills = FakeRaceSkillsService(db, resolved=resolved_skills)
    service._ability_bonuses = FakeRaceAbilityBonusService(db)
    service._nested_features = FakeNestedFeatureService(db)
    return service, db


def make_ability_bonus_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = RaceAbilityBonusService(db)
    service.repository = FakeRaceRepository(db, existing_by_id=existing_by_id)
    return service, db


def make_skill_service(existing_by_id=None, skills=None):
    db = FakeAsyncSession()
    service = RaceSkillService(db)
    service.repository = FakeRaceRepository(db, existing_by_id=existing_by_id, skills=skills)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceCrudService:
    async def test_create_race_without_nested_capabilities(self):
        service, db = make_crud_service(resolved_skills=None)

        result = await service.create_race(RaceCreate(name="Elf", speed=35))

        assert result.id == 1
        assert result.name == "Elf"
        assert result.speed == 35
        assert db.commits == 1
        assert service._nested_features.created == [(FeatureSourceType.RACE, 1, None, False)]
        assert service._ability_bonuses.calls == []
        assert service._skills.set_calls == []

    async def test_create_race_with_bonuses_skills_and_features(self):
        skill = make_skill()
        service, db = make_crud_service(resolved_skills=[skill])
        data = RaceCreate(
            name="Elf",
            ability_bonuses=[AbilityBonusItem(ability=AbilityScore.DEX, bonus=2)],
            granted_skills=[1],
            features=[NestedFeatureCreate(name="Keen Senses", description="d")],
        )

        result = await service.create_race(data)

        assert result.id == 1
        assert result.ability_bonuses[0].ability == AbilityScore.DEX
        assert result.ability_bonuses[0].bonus == 2
        assert result.granted_skills[0].id == 1
        assert db.commits == 1
        assert service._skills.resolve_calls == [[1]]
        assert service._ability_bonuses.calls[0][1] == [{"ability": AbilityScore.DEX, "bonus": 2}]
        assert service._ability_bonuses.calls[0][2] is False
        assert service._skills.set_calls == [(service.repository._rows[1], [skill], False)]
        assert service._nested_features.created == [(FeatureSourceType.RACE, 1, data.features, False)]

    async def test_create_race_rolls_back_when_persist_fails(self):
        service, db = make_crud_service(resolved_skills=None)

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_race(RaceCreate(name="Elf"))

        assert db.rollbacks == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceAbilityBonusService:
    async def test_set_ability_bonuses_replaces_and_returns_race(self):
        service, db = make_ability_bonus_service(existing_by_id={1: make_race()})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        result = await service.set_ability_bonuses(1, data)

        assert result.ability_bonuses[0].ability == AbilityScore.INT
        assert result.ability_bonuses[0].bonus == 1
        assert service.repository.set_ability_bonuses_calls[0][0].id == 1
        assert service.repository.set_ability_bonuses_calls[0][1] == [{"ability": AbilityScore.INT, "bonus": 1}]
        assert service.repository.set_ability_bonuses_calls[0][2] is True
        assert db.commits == 1

    async def test_set_ability_bonuses_raises_when_race_missing(self):
        service, _ = make_ability_bonus_service(existing_by_id={})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        with pytest.raises(RecordNotFoundError):
            await service.set_ability_bonuses(99, data)

    async def test_set_ability_bonuses_for_race_delegates_without_commit(self):
        race = make_race()
        service, db = make_ability_bonus_service()

        await service.set_ability_bonuses_for_race(race, [{"ability": AbilityScore.STR, "bonus": 1}], commit=False)

        assert service.repository.set_ability_bonuses_calls == [
            (race, [{"ability": AbilityScore.STR, "bonus": 1}], False)
        ]
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceSkillService:
    async def test_resolve_skills_returns_none_for_empty_input(self):
        service, _ = make_skill_service()

        assert await service.resolve_skills(None) is None
        assert await service.resolve_skills([]) is None

    async def test_resolve_skills_returns_rows_for_valid_ids(self):
        service, _ = make_skill_service(skills={1: make_skill()})

        result = await service.resolve_skills([1])

        assert [skill.id for skill in result] == [1]
        assert service.repository.get_skills_calls == [[1]]

    async def test_set_skills_replaces_granted_skills(self):
        race = make_race()
        service, db = make_skill_service(existing_by_id={1: race}, skills={1: make_skill()})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[1]))

        assert result.granted_skills[0].id == 1
        assert service.repository.set_skills_calls == [(race, [race.granted_skills[0]], True)]
        assert db.commits == 1

    async def test_set_skills_with_empty_ids_calls_repository_with_none(self):
        race = make_race()
        service, _ = make_skill_service(existing_by_id={1: race})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[]))

        assert result.granted_skills == []
        assert service.repository.set_skills_calls == [(race, None, True)]

    async def test_set_skills_raises_when_race_missing(self):
        service, _ = make_skill_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_skills(99, SkillsUpdate(skill_ids=[1]))

    async def test_set_skills_for_race_delegates_without_commit(self):
        race = make_race()
        skill = make_skill()
        service, db = make_skill_service()

        await service.set_skills_for_race(race, [skill], commit=False)

        assert service.repository.set_skills_calls == [(race, [skill], False)]
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceRepository:
    async def test_get_subrace_returns_subrace_when_owned(self):
        session = FakeAsyncSession(scalar_results=[make_subrace(id=1, race_id=5)])
        repository = RaceRepository(session)

        result = await repository.get_subrace(5, 1)

        assert result.id == 1

    async def test_get_subrace_returns_none_when_owned_by_other_race(self):
        session = FakeAsyncSession(scalar_results=[make_subrace(id=1, race_id=7)])
        repository = RaceRepository(session)

        result = await repository.get_subrace(5, 1)

        assert result is None

    async def test_set_ability_bonuses_replaces_child_rows_and_commits(self):
        session = FakeAsyncSession()
        repository = RaceRepository(session)
        race = make_race()

        result = await repository.set_ability_bonuses(
            race, [{"ability": AbilityScore.DEX, "bonus": 2}, {"ability": AbilityScore.INT, "bonus": 1}]
        )

        assert result is race
        assert len(session.added) == 2
        assert all(isinstance(row, RaceAbilityBonus) for row in session.added)
        assert session.added[0].ability == AbilityScore.DEX
        assert session.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceSkillsRepository:
    async def test_set_skills_replaces_association_and_commits(self):
        session = FakeAsyncSession()
        repository = RaceSkillsRepository(session)
        race = make_race()

        result = await repository.set_skills(race, [make_skill(), make_skill(id=2, name="Acrobatics")])

        assert result is race
        assert len(session.executes) == 2
        assert session.commits == 1

    async def test_set_skills_with_empty_list_and_no_commit_flushes(self):
        session = FakeAsyncSession()
        repository = RaceSkillsRepository(session)
        race = make_race()

        await repository.set_skills(race, [], commit=False)

        assert session.flushes == 1
        assert session.commits == 0

    async def test_set_skills_with_none_clears_association(self):
        session = FakeAsyncSession()
        repository = RaceSkillsRepository(session)
        race = make_race()

        result = await repository.set_skills(race, None)

        assert result is race
        assert session.commits == 1

    async def test_get_skills_by_ids_looks_up_rows(self):
        skill = make_skill()
        session = FakeAsyncSession(execute_results=[FakeResult([skill])])
        repository = RaceSkillsRepository(session)

        result = await repository.get_skills_by_ids([1])

        assert result == [skill]
        assert len(session.executes) == 1
