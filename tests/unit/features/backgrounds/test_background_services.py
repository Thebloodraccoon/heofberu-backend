"""Unit tests for the background crud / skills / features services and repositories."""

from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, BackgroundSuggestionType
from app.core.base.transaction import atomic
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate
from app.features.backgrounds.crud.service import BackgroundCrudService
from app.features.backgrounds.features.service import BackgroundFeatureService
from app.features.backgrounds.skills.repository import BackgroundSkillsRepository
from app.features.backgrounds.skills.schemas import SkillsUpdate
from app.features.backgrounds.skills.service import BackgroundSkillsService
from app.features.backgrounds.suggestions.exceptions import LastSuggestionOfTypeError
from app.features.backgrounds.suggestions.schemas import SuggestionUpdate
from app.features.backgrounds.suggestions.service import BackgroundSuggestionsService
from app.models import Background, BackgroundSuggestion, Feature
from app.models.skill_model import Skill
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_background(**overrides) -> Background:
    base = {
        "id": 1,
        "name": "Criminal",
        "description": "",
        "starting_gold": 0,
        "granted_skills": [],
        "starting_items": [],
        "suggestions": [],
    }
    base.update(overrides)
    return Background(**base)


def make_skill(**overrides) -> Skill:
    base = {
        "id": 1,
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
        self.bare_calls = []
        self.suggestion_calls = []
        self.deleted_suggestions = []

    async def create(self, payload):
        row = Background(
            id=self._next_id,
            name=payload["name"],
            description=payload.get("description", ""),
            starting_gold=payload.get("starting_gold", 0),
            granted_skills=[],
            starting_items=[],
            suggestions=[],
        )
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        return row

    async def set_skills(self, background_id: int, skills: list[Skill] | None) -> None:
        self.set_skills_calls.append((background_id, skills))
        background = self._rows.get(background_id)
        if background is not None:
            background.granted_skills = list(skills or [])

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        self.get_skills_calls.append(skill_ids)
        return [self.skills[skill_id] for skill_id in skill_ids if skill_id in self.skills]

    async def get_bare(self, background_id: int):
        self.bare_calls.append(background_id)
        return self._rows.get(background_id)

    async def set_suggestions(self, background, suggestions):
        self.suggestion_calls.append((background, suggestions))
        rows = [
            BackgroundSuggestion(
                id=index + 1, background_id=background.id, suggestion_type=entry.suggestion_type, text=entry.text
            )
            for index, entry in enumerate(suggestions)
        ]
        background.suggestions = rows
        return rows

    async def lock_background(self, background_id: int) -> bool:
        return background_id in self._rows

    async def get_suggestion(self, background_id: int, suggestion_id: int):
        background = self._rows.get(background_id)
        if background is None:
            return None
        return next((row for row in background.suggestions if row.id == suggestion_id), None)

    async def count_of_type(self, background_id: int, suggestion_type) -> int:
        background = self._rows[background_id]
        return sum(1 for row in background.suggestions if row.suggestion_type == suggestion_type)

    async def update_suggestion(self, suggestion, data):
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(suggestion, field, value)
        return suggestion

    async def delete_suggestion(self, suggestion):
        self.deleted_suggestions.append(suggestion)


class FakeBackgroundFeaturesService:
    """Stands in for BackgroundFeatureService inside BackgroundCrudService."""

    def __init__(self, db, features=None):
        self.db = db
        self.features = features or []
        self.list_calls = []
        self.invalidate_calls = 0

    async def list_features(self, source_id):
        self.list_calls.append(source_id)
        return self.features

    async def list_for_source(self, source_type, source_id):
        self.list_calls.append(source_id)
        return self.features

    async def invalidate(self):
        self.invalidate_calls += 1


@pytest.fixture(autouse=True)
def purged(monkeypatch):
    """Record cache purges instead of touching Redis; yields the list of purged namespaces."""

    calls: list[str] = []

    async def record(namespace):
        calls.append(namespace)

    monkeypatch.setattr("app.core.base.service.invalidate", record)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", record)
    return calls


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr("app.features.characters.progression.feature_sync.reconcile_characters_for_source", AsyncMock())


def make_crud_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = BackgroundCrudService(db)
    service.repository = FakeBackgroundRepository(db, existing_by_id=existing_by_id)
    service._suggestions = service.repository
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
    async def test_create_background_persists_base_fields_and_invalidates_cache(self):
        service, db = make_crud_service()

        result = await service.create_background(BackgroundCreate(name="Criminal"))

        assert result.id == 1
        assert result.name == "Criminal"
        assert db.commits == 1

    async def test_create_background_seeds_four_placeholder_suggestions_in_same_transaction(self):
        """A fresh background gets one text="-" suggestion per type, flushed not committed separately."""
        service, db = make_crud_service()

        await service.create_background(BackgroundCreate(name="Criminal"))

        background, suggestions = service.repository.suggestion_calls[0]
        assert background.id == 1
        assert {(entry.suggestion_type, entry.text) for entry in suggestions} == {
            (BackgroundSuggestionType.PERSONALITY_TRAIT, "-"),
            (BackgroundSuggestionType.IDEAL, "-"),
            (BackgroundSuggestionType.BOND, "-"),
            (BackgroundSuggestionType.FLAW, "-"),
        }
        assert db.commits == 1

    async def test_create_background_does_not_touch_skill_or_feature_capabilities(self):
        """granted_skills/features are attached via their own endpoints, not at creation."""
        service, _ = make_crud_service()

        await service.create_background(BackgroundCreate(name="Criminal"))

        assert service.repository.set_skills_calls == []

    async def test_create_background_propagates_persist_failure(self):
        service, _ = make_crud_service()

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_background(BackgroundCreate(name="Criminal"))

    async def test_get_by_id_returns_full_response_with_features(self):
        feature = Feature(
            id=3,
            name="Steady",
            description="",
            source_type="BACKGROUND",
            background_id=1,
            has_static_effects=False,
            has_choices=False,
        )
        service, db = make_crud_service(existing_by_id={1: make_background(features=[feature])})

        result = await service.get_by_id(1)

        assert result.id == 1
        assert result.features[0].id == 3
        assert result.features[0].name == "Steady"
        assert db.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundSkillsService:
    async def test_set_skills_replaces_granted_skills(self):
        background = make_background()
        skill = make_skill()
        service, db = make_skills_service(existing_by_id={1: background}, skills={1: skill})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[1]))

        assert result.granted_skills[0].id == 1
        assert service.repository.set_skills_calls == [(background.id, [skill])]
        assert db.commits == 1

    async def test_set_skills_raises_when_background_missing(self):
        service, _ = make_skills_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_skills(99, SkillsUpdate(skill_ids=[1]))


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundRepository:
    async def test_is_in_use_is_a_single_exists_query(self):
        """One EXISTS scalar however many features/characters match (no MultipleResultsFound)."""
        session = FakeAsyncSession(scalar_results=[True])
        repository = BackgroundRepository(session)

        assert await repository.is_in_use(1) is True
        assert session.executes == []

    async def test_is_in_use_false_when_nothing_granted(self):
        session = FakeAsyncSession(scalar_results=[False])
        repository = BackgroundRepository(session)

        assert await repository.is_in_use(1) is False

    async def test_delete_locks_features_before_checking_the_guard(self):
        session = FakeAsyncSession(scalar_results=[True])
        repository = BackgroundRepository(session)

        with pytest.raises(RecordInUseError):
            await repository.delete(make_background())

        assert "FOR UPDATE" in str(session.executes[0])
        assert session.deleted == []

    async def test_delete_removes_the_row_when_unused(self):
        session = FakeAsyncSession(scalar_results=[False])
        repository = BackgroundRepository(session)
        background = make_background()

        async with atomic(session):
            assert await repository.delete(background) is True
        assert session.deleted == [background]
        assert session.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundSkillsRepository:
    async def test_set_skills_replaces_association_and_commits(self):
        session = FakeAsyncSession()
        repository = BackgroundSkillsRepository(session)
        background = make_background()

        async with atomic(session):
            await repository.set_skills(background.id, [make_skill()])

        assert len(session.executes) == 2
        assert session.commits == 1

    async def test_set_skills_with_empty_list_flushes_inside_atomic(self):
        session = FakeAsyncSession()
        repository = BackgroundSkillsRepository(session)
        background = make_background()

        async with atomic(session):
            await repository.set_skills(background.id, [])
            assert session.flushes == 1
            assert session.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundFeatureService:
    async def test_list_features_delegates_to_feature_crud(self):
        service, _ = make_feature_service(existing_by_id={1: make_background()})

        result = await service.list_features(1)

        assert result == []

    async def test_list_features_raises_when_background_missing(self):
        service, _ = make_feature_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.list_features(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackgroundCachePurges:
    async def test_create_purges_only_the_background_listing_after_commit(self, purged):
        service, _ = make_crud_service()

        await service.create_background(BackgroundCreate(name="Criminal"))

        assert purged == ["backgrounds"]

    async def test_delete_reads_the_bare_row_and_purges_dependent_namespaces(self, purged):
        service, db = make_crud_service(existing_by_id={1: make_background()})

        assert await service.delete(1) is True

        assert service.repository.bare_calls == [1]
        assert set(purged) == {"backgrounds", "background_features", "features", "nested_items"}

    async def test_delete_missing_background_raises_not_found(self, purged):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)

        assert purged == []

    async def test_skill_replacement_purges_only_backgrounds(self, purged):
        service, _ = make_skills_service(existing_by_id={1: make_background()}, skills={1: make_skill()})

        await service.set_skills(1, SkillsUpdate(skill_ids=[1]))

        assert purged == ["backgrounds"]


def make_suggestions_service(background):
    db = FakeAsyncSession()
    service = BackgroundSuggestionsService(db)
    service.repository = FakeBackgroundRepository(db, existing_by_id={background.id: background})
    return service


def suggestion(id, suggestion_type, background_id=1):
    return BackgroundSuggestion(id=id, background_id=background_id, suggestion_type=suggestion_type, text="x")


@pytest.mark.unit
@pytest.mark.asyncio
class TestLastSuggestionOfTypeGuard:
    async def test_deleting_the_last_suggestion_of_a_type_is_refused(self, purged):
        background = make_background(suggestions=[suggestion(1, BackgroundSuggestionType.BOND)])
        service = make_suggestions_service(background)

        with pytest.raises(LastSuggestionOfTypeError):
            await service.delete_suggestion(1, 1)

        assert service.repository.deleted_suggestions == []
        assert purged == []

    async def test_deleting_one_of_several_of_a_type_is_allowed(self, purged):
        background = make_background(
            suggestions=[suggestion(1, BackgroundSuggestionType.BOND), suggestion(2, BackgroundSuggestionType.BOND)]
        )
        service = make_suggestions_service(background)

        await service.delete_suggestion(1, 1)

        assert len(service.repository.deleted_suggestions) == 1
        assert purged == ["backgrounds"]

    async def test_retyping_the_last_suggestion_of_a_type_is_refused(self):
        background = make_background(suggestions=[suggestion(1, BackgroundSuggestionType.BOND)])
        service = make_suggestions_service(background)

        with pytest.raises(LastSuggestionOfTypeError):
            await service.update_suggestion(1, 1, SuggestionUpdate(suggestion_type=BackgroundSuggestionType.FLAW))

    async def test_editing_the_text_of_the_last_suggestion_is_allowed(self):
        background = make_background(suggestions=[suggestion(1, BackgroundSuggestionType.BOND)])
        service = make_suggestions_service(background)

        result = await service.update_suggestion(1, 1, SuggestionUpdate(text="new"))

        assert result.text == "new"

    async def test_missing_background_raises_not_found(self):
        service = make_suggestions_service(make_background())

        with pytest.raises(RecordNotFoundError):
            await service.delete_suggestion(99, 1)
