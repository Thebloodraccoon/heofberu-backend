"""Unit tests for the skill schemas, delete guard and cache namespaces."""

from pydantic import ValidationError
import pytest

from app.core.exceptions import RecordInUseError
from app.features.skills.cache import SKILL_CACHE_NAMESPACES, SKILL_DEPENDENT_CACHE_NAMESPACES
from app.features.skills.crud.repository import SkillRepository
from app.features.skills.crud.schemas import SkillCreate, SkillUpdate
from app.features.skills.crud.service import SkillCrudService
from app.models import Skill
from tests.unit.fakes import FakeAsyncSession, FakeRepository


@pytest.fixture(autouse=True)
def purged(monkeypatch):
    calls: list[str] = []

    async def record(namespace):
        calls.append(namespace)

    monkeypatch.setattr("app.core.base.service.invalidate", record)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", record)
    return calls


def make_service(rows=()):
    db = FakeAsyncSession()
    service = SkillCrudService(db)
    service.repository = FakeRepository(db, existing_by_id={row.id: row for row in rows}, model=Skill)
    return service


@pytest.mark.unit
class TestSkillSchemas:
    def test_create_strips_and_bounds_the_name(self):
        assert SkillCreate(name="  Stealth ", ability="DEX").name == "Stealth"
        for name in ("", "  ", "x" * 101):
            with pytest.raises(ValidationError):
                SkillCreate(name=name, ability="DEX")

    @pytest.mark.parametrize("field", ["name", "ability", "description"])
    def test_update_rejects_explicit_null(self, field):
        with pytest.raises(ValidationError):
            SkillUpdate(**{field: None})

    def test_namespaces_cover_every_cache_embedding_skill_names(self):
        assert SKILL_CACHE_NAMESPACES[0] == "skills"
        assert {
            "classes",
            "races",
            "backgrounds",
            "features",
            "feats",
            "class_features",
            "subclass_features",
            "race_features",
            "subrace_features",
            "background_features",
        } <= set(SKILL_DEPENDENT_CACHE_NAMESPACES)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSkillCaching:
    async def test_create_purges_only_the_skill_listing(self, purged):
        service = make_service()

        await service.create(SkillCreate(name="Stealth", ability="DEX"))

        assert purged == ["skills"]

    async def test_update_purges_every_dependent_namespace(self, purged):
        service = make_service([Skill(id=1, name="Stealth", ability="DEX", description="")])

        await service.update(1, SkillUpdate(name="Sneaking"))

        assert set(purged) == set(SKILL_CACHE_NAMESPACES)

    async def test_delete_purges_only_the_skill_listing(self, purged):
        service = make_service([Skill(id=1, name="Stealth", ability="DEX", description="")])

        await service.delete(1)

        assert purged == ["skills"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestSkillRepositoryGuard:
    async def test_is_in_use_checks_feature_effects_too(self):
        statements = []

        class Session(FakeAsyncSession):
            async def scalar(self, stmt):
                statements.append(str(stmt))
                return True

        assert await SkillRepository(Session()).is_in_use(1) is True
        assert "feature_skill_proficiency_effects" in statements[0]
        assert "character_proficiencies" in statements[0]

    async def test_delete_locks_the_row_and_respects_the_guard(self):
        session = FakeAsyncSession(scalar_results=[True])
        repository = SkillRepository(session)

        with pytest.raises(RecordInUseError):
            await repository.delete(Skill(id=1, name="Stealth", ability="DEX", description=""))

        assert "FOR UPDATE" in str(session.executes[0])
