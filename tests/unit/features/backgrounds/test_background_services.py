"""Unit tests for the background crud / skills / features services and repositories."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType
from app.core.exceptions import RecordNotFoundError
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate
from app.features.backgrounds.crud.service import BackgroundCrudService
from app.features.backgrounds.features.service import BackgroundFeatureService
from app.features.backgrounds.skills.repository import BackgroundSkillsRepository
from app.features.backgrounds.skills.schemas import SkillsUpdate
from app.features.backgrounds.skills.service import BackgroundSkillsService
from app.features.shared.features.schemas import NestedFeatureCreate
from app.models.background_model import Background
from app.models.skill_model import Skill
from tests.unit.fakes import FakeAsyncSession, FakeRepository, FakeResult


def make_background(**overrides) -> Background:
    base = {
        "id": 1,
        "name": "Criminal",
        "personality_traits_suggestions": "",
        "ideals_suggestions": "",
        "bonds_suggestions": "",
        "flaws_suggestions": "",
        "description": "",
        "created_by_id": None,
        "granted_skills": [],
        "starting_items": [],
    }
    base.update(overrides)
    return Background(**base)


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


class FakeBackgroundRepository(FakeRepository):
    """Background repository stand-in with the capability methods the services need."""

    def __init__(self, db, existing_by_id=None, skills=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Background)
        self.skills = skills or {}
        self.set_skills_calls = []
        self.get_skills_calls = []

    async def create(self, payload, *, commit=True):
        row = Background(
            id=self._next_id,
            name=payload["name"],
            personality_traits_suggestions=payload.get("personality_traits_suggestions", ""),
            ideals_suggestions=payload.get("ideals_suggestions", ""),
            bonds_suggestions=payload.get("bonds_suggestions", ""),
            flaws_suggestions=payload.get("flaws_suggestions", ""),
            description=payload.get("description", ""),
            created_by_id=payload.get("created_by_id"),
            granted_skills=[],
            starting_items=[],
        )
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        if commit:
            await self.db.commit()
        return row

    async def set_skills(
        self, background: Background, skills: list[Skill] | None, *, commit: bool = True
    ) -> Background:
        self.set_skills_calls.append((background, skills, commit))
        background.granted_skills = list(skills or [])
        if commit:
            await self.db.commit()
        return background

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        self.get_skills_calls.append(skill_ids)
        return [self.skills[skill_id] for skill_id in skill_ids if skill_id in self.skills]


class FakeBackgroundSkillsService:
    """Stands in for BackgroundSkillsService inside BackgroundCrudService."""

    def __init__(self, db, resolved=None):
        self.db = db
        self.resolved = resolved
        self.resolve_calls = []
        self.set_calls = []

    async def resolve_skills(self, skill_ids):
        self.resolve_calls.append(skill_ids)
        return self.resolved

    async def set_skills_for_background(self, background, skills, *, commit=True):
        self.set_calls.append((background, skills, commit))
        background.granted_skills = list(skills or [])


class FakeBackgroundFeaturesService:
    """Stands in for BackgroundFeatureService inside BackgroundCrudService."""

    def __init__(self, db, features=None):
        self.db = db
        self.features = features or []
        self.list_calls = []
        self.create_calls = []
        self.invalidate_calls = 0

    async def list_features(self, source_id):
        self.list_calls.append(source_id)
        return self.features

    async def list_for_source(self, source_type, source_id):
        self.list_calls.append(source_id)
        return self.features

    async def create_feature_for_source(self, source_type, source_id, item, created_by_id, *, commit=False):
        self.create_calls.append((source_type, source_id, item, created_by_id, commit))
        return SimpleNamespace(id=1, name=item.name, description=item.description, level=item.level)

    async def invalidate(self):
        self.invalidate_calls += 1


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    """Stop generic cache invalidation from touching Redis."""
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture(autouse=True)
def no_background_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.backgrounds.crud.service.invalidate_background_cache", AsyncMock())
    monkeypatch.setattr("app.features.backgrounds.features.service.invalidate_background_cache", AsyncMock())


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.feature_sync.reconcile_characters_for_source", AsyncMock())


def make_crud_service(existing_by_id=None, resolved_skills=None, features=None):
    db = FakeAsyncSession()
    service = BackgroundCrudService(db)
    service.repository = FakeBackgroundRepository(db, existing_by_id=existing_by_id)
    service._skills = FakeBackgroundSkillsService(db, resolved=resolved_skills)
    service._features = FakeBackgroundFeaturesService(db, features=features)
    return service, db


def make_skills_service(existing_by_id=None, skills=None):
    db = FakeAsyncSession()
    service = BackgroundSkillsService(db)
    service.repository = FakeBackgroundRepository(db, existing_by_id=existing_by_id, skills=skills)
    return service, db


def make_feature_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = BackgroundFeatureService(db)
    service.repository = FakeBackgroundRepository(db, existing_by_id=existing_by_id)
    service._features = FakeBackgroundFeaturesService(db)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundCrudService:
    async def test_create_background_without_skills(self):
        service, db = make_crud_service(resolved_skills=None)

        result = await service.create_background(BackgroundCreate(name="Criminal"), created_by_id=3)

        assert result.id == 1
        assert result.name == "Criminal"
        assert db.commits == 1
        assert service.repository.created[0].created_by_id == 3
        assert service._skills.resolve_calls == [None]
        assert service._skills.set_calls == []
        assert service._features.list_calls == [1]

    async def test_create_background_with_granted_skills(self):
        skill = make_skill()
        service, db = make_crud_service(resolved_skills=[skill])

        result = await service.create_background(BackgroundCreate(name="Criminal", granted_skills=[1]))

        assert result.id == 1
        assert result.granted_skills[0].id == 1
        assert service._skills.set_calls == [(service.repository._rows[1], [skill], False)]

    async def test_create_background_rolls_back_when_persist_fails(self):
        service, db = make_crud_service(resolved_skills=None)

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_background(BackgroundCreate(name="Criminal"))

        assert db.rollbacks == 1

    async def test_get_by_id_returns_full_response_with_features(self):
        service, db = make_crud_service(
            existing_by_id={1: make_background()},
            features=[SimpleNamespace(id=3, name="Steady", description="", level=None)],
        )

        result = await service.get_by_id(1)

        assert result.id == 1
        assert result.features[0].id == 3
        assert result.features[0].name == "Steady"
        assert service._features.list_calls == [1]
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundSkillsService:
    async def test_resolve_skills_returns_none_for_empty_input(self):
        service, _ = make_skills_service()

        assert await service.resolve_skills(None) is None
        assert await service.resolve_skills([]) is None

    async def test_set_skills_replaces_granted_skills(self):
        background = make_background()
        skill = make_skill()
        service, db = make_skills_service(existing_by_id={1: background}, skills={1: skill})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[1]))

        assert result.granted_skills[0].id == 1
        assert service.repository.set_skills_calls == [(background, [skill], True)]
        assert db.commits == 1

    async def test_set_skills_raises_when_background_missing(self):
        service, _ = make_skills_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_skills(99, SkillsUpdate(skill_ids=[1]))

    async def test_set_skills_for_background_delegates_without_commit(self):
        background = make_background()
        skill = make_skill()
        service, db = make_skills_service()

        await service.set_skills_for_background(background, [skill], commit=False)

        assert service.repository.set_skills_calls == [(background, [skill], False)]
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundRepository:
    async def test_is_in_use_false_when_no_features(self):
        session = FakeAsyncSession(execute_results=[FakeResult([])])
        repository = BackgroundRepository(session)

        assert await repository.is_in_use(1) is False

    async def test_is_in_use_false_when_features_not_granted(self):
        session = FakeAsyncSession(execute_results=[FakeResult([[1]]), FakeResult([])])
        repository = BackgroundRepository(session)

        assert await repository.is_in_use(1) is False

    async def test_is_in_use_true_when_feature_granted(self):
        session = FakeAsyncSession(execute_results=[FakeResult([[1]]), FakeResult([SimpleNamespace()])])
        repository = BackgroundRepository(session)

        assert await repository.is_in_use(1) is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundSkillsRepository:
    async def test_set_skills_replaces_association_and_commits(self):
        session = FakeAsyncSession()
        repository = BackgroundSkillsRepository(session)
        background = make_background()

        result = await repository.set_skills(background, [make_skill()])

        assert result is background
        assert len(session.executes) == 2
        assert session.commits == 1

    async def test_set_skills_with_empty_list_and_no_commit_flushes(self):
        session = FakeAsyncSession()
        repository = BackgroundSkillsRepository(session)
        background = make_background()

        await repository.set_skills(background, [], commit=False)

        assert session.flushes == 1
        assert session.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundFeatureService:
    async def test_add_feature_runs_super_and_invalidates_background_cache(self):
        service, db = make_feature_service(existing_by_id={1: make_background()})
        data = NestedFeatureCreate(name="Steady", description="d")

        result = await service.add_feature(1, data, created_by_id=7)

        assert result.id == 1
        assert result.name == "Steady"
        assert service._features.create_calls == [(FeatureSourceType.BACKGROUND, 1, data, 7, False)]
        assert service._features.invalidate_calls == 1
        assert db.commits == 1

    async def test_list_features_delegates_to_nested_service(self):
        service, _ = make_feature_service(existing_by_id={1: make_background()})

        result = await service.list_features(1)

        assert result == []
