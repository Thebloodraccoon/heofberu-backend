"""
Unit tests for the race crud / ability-bonus / skill / tag / feature services and repositories.

Services run on recording fake repositories, so the service bodies (which the
HTTP-level integration tests do not trace) are covered directly: the exact
cache namespaces each write purges, the post-commit ordering, and the cascade
cleanup on delete.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType, RaceSize
from app.core.exceptions import RecordNotFoundError
from app.features.races.ability_bonuses.service import RaceAbilityBonusService
from app.features.races.crud.repository import RaceRepository
from app.features.races.crud.schemas import RaceCreate, RaceUpdate
from app.features.races.crud.service import RaceCrudService
from app.features.races.features.service import RaceFeatureService
from app.features.races.skills.repository import RaceSkillsRepository
from app.features.races.skills.schemas import SkillsUpdate
from app.features.races.skills.service import RaceSkillService
from app.features.races.tags.service import RaceTagService
from app.features.shared.catalog.schemas import AbilityBonusesUpdate, AbilityBonusItem
from app.features.shared.tags.schemas import TagsUpdate
from app.models.races.race_association_models import RaceAbilityBonus
from app.models.races.race_model import Race
from app.models.skill_model import Skill
from app.models.tag_model import Tag
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
        "tags": [],
    }
    base.update(overrides)
    return Race(**base)


def make_skill(**overrides) -> Skill:
    base = {"id": 1, "name": "Perception", "ability": AbilityScore.WIS, "description": ""}
    base.update(overrides)
    return Skill(**base)


def make_subrace(**overrides):
    base = {"id": 1, "race_id": 1, "name": "High Elf", "description": "", "ability_bonuses": []}
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeRaceRepository(FakeRepository):
    """Race repository stand-in with the capability methods the services need."""

    def __init__(self, db, existing_by_id=None, skills=None, tags=None, subrace_ids=()):
        super().__init__(db, existing_by_id=existing_by_id, model=Race)
        self.skills = skills or {}
        self.tags = tags or {}
        self.subrace_ids = list(subrace_ids)
        self.set_ability_bonuses_calls = []
        self.set_skills_calls = []
        self.set_tags_calls = []

    async def create(self, payload, *, commit=True):
        row = make_race(id=self._next_id, **payload)
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        if commit:
            await self.db.commit()
        return row

    async def list_subrace_ids(self, race_id: int) -> list[int]:
        return self.subrace_ids

    async def set_ability_bonuses(self, race_id: int, bonuses: list[dict], *, commit: bool = True) -> None:
        self.set_ability_bonuses_calls.append((race_id, bonuses, commit))
        race = self._rows.get(race_id)
        if race is not None:
            race.ability_bonuses = [
                RaceAbilityBonus(race_id=race_id, ability=bonus["ability"], bonus=bonus["bonus"]) for bonus in bonuses
            ]
        if commit:
            await self.db.commit()

    async def set_skills(self, race_id: int, skills: list[Skill] | None, *, commit: bool = True) -> None:
        self.set_skills_calls.append((race_id, skills, commit))
        race = self._rows.get(race_id)
        if race is not None:
            race.granted_skills = list(skills or [])
        if commit:
            await self.db.commit()

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        return [self.skills[skill_id] for skill_id in skill_ids if skill_id in self.skills]

    async def set_tags(self, race_id: int, tags: list[Tag] | None, *, commit: bool = True) -> None:
        self.set_tags_calls.append((race_id, tags, commit))
        race = self._rows.get(race_id)
        if race is not None:
            race.tags = list(tags or [])
        if commit:
            await self.db.commit()

    async def get_tags_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        return [self.tags[tag_id] for tag_id in tag_ids if tag_id in self.tags]


class FakeStorage:
    def __init__(self):
        self.deleted = []

    async def delete_image(self, entity, row_id):
        self.deleted.append((entity, row_id))


@pytest.fixture(autouse=True)
def purges(monkeypatch):
    """Record cache purges (namespaces per ``invalidate_many`` call) instead of touching Redis."""

    calls: list[list[str]] = []

    async def fake_invalidate_many(namespaces, keys=None):
        calls.append(list(namespaces))

    monkeypatch.setattr("app.features.shared.catalog.cache.invalidate_many", fake_invalidate_many)
    monkeypatch.setattr("app.features.races.cache.invalidate_many", fake_invalidate_many)
    return calls


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr(
        "app.features.characters.progression.source_bonuses.reconcile_characters_for_source", AsyncMock()
    )


def make_crud_service(existing_by_id=None, subrace_ids=(), storage=None):
    db = FakeAsyncSession()
    service = RaceCrudService(db, storage)
    service.repository = FakeRaceRepository(db, existing_by_id=existing_by_id, subrace_ids=subrace_ids)
    return service, db


def make_service(cls, existing_by_id=None, **repository_kwargs):
    db = FakeAsyncSession()
    service = cls(db)
    service.repository = FakeRaceRepository(db, existing_by_id=existing_by_id, **repository_kwargs)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceCrudService:
    async def test_create_race_persists_base_fields_and_purges_races(self, purges):
        service, db = make_crud_service()

        result = await service.create_race(RaceCreate(name="Elf", speed=35))

        assert (result.id, result.name, result.speed) == (1, "Elf", 35)
        assert db.commits == 1
        assert purges == [["races", "spells"]]

    async def test_create_race_propagates_persist_failure_without_purging(self, purges):
        service, _ = make_crud_service()

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_race(RaceCreate(name="Elf"))

        assert purges == []

    async def test_update_purges_only_the_races_namespace(self, purges):
        service, _ = make_crud_service(existing_by_id={1: make_race(speed=30)})

        result = await service.update(1, RaceUpdate(speed=35, description="Tall"))

        assert (result.speed, result.description) == (35, "Tall")
        assert purges == [["races", "spells"]]

    async def test_update_missing_race_raises_without_purging(self, purges):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update(9, RaceUpdate(speed=35))

        assert purges == []

    async def test_delete_purges_cascade_namespaces_and_drops_images(self, purges):
        race = make_race()
        storage = FakeStorage()
        service, _ = make_crud_service(existing_by_id={1: race}, subrace_ids=[4, 5], storage=storage)

        assert await service.delete(1) is True

        assert service.repository.deleted == [race]
        assert purges == [["races", "race_features", "subrace_features", "features", "spells"]]
        assert storage.deleted == [("races", 1), ("subraces", 4), ("subraces", 5)]

    async def test_delete_without_storage_still_purges(self, purges):
        service, _ = make_crud_service(existing_by_id={1: make_race()})

        await service.delete(1)

        assert purges == [["races", "race_features", "subrace_features", "features", "spells"]]

    async def test_delete_blocked_race_keeps_cache_and_images(self, purges):
        storage = FakeStorage()
        service, _ = make_crud_service(existing_by_id={1: make_race()}, storage=storage)

        async def in_use(race):
            raise RuntimeError("in use")

        service.repository.delete = in_use

        with pytest.raises(RuntimeError):
            await service.delete(1)

        assert purges == []
        assert storage.deleted == []

    async def test_delete_missing_race_raises(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceAbilityBonusService:
    async def test_set_ability_bonuses_replaces_in_one_transaction_and_reconciles(self, purges):
        from app.features.characters.progression import source_bonuses as module

        service, db = make_service(RaceAbilityBonusService, existing_by_id={1: make_race()})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        result = await service.set_ability_bonuses(1, data)

        assert result.ability_bonuses[0].ability == AbilityScore.INT
        assert result.ability_bonuses[0].bonus == 1
        assert service.repository.set_ability_bonuses_calls == [(1, [{"ability": AbilityScore.INT, "bonus": 1}], False)]
        assert db.commits == 1
        module.reconcile_characters_for_source.assert_awaited_once_with(db, FeatureSourceType.RACE, 1)
        assert purges == [["races"]]

    async def test_cache_is_purged_only_after_commit(self, monkeypatch):
        events = []
        service, db = make_service(RaceAbilityBonusService, existing_by_id={1: make_race()})

        async def commit():
            events.append("commit")

        async def purge(namespaces, keys=None):
            events.append("purge")

        monkeypatch.setattr(db, "commit", commit)
        monkeypatch.setattr("app.features.shared.catalog.cache.invalidate_many", purge)

        await service.set_ability_bonuses(1, AbilityBonusesUpdate(ability_bonuses=[]))

        assert events == ["commit", "purge"]

    async def test_failed_reconcile_rolls_back_and_skips_the_purge(self, monkeypatch, purges):
        service, db = make_service(RaceAbilityBonusService, existing_by_id={1: make_race()})
        monkeypatch.setattr(
            "app.features.characters.progression.source_bonuses.reconcile_characters_for_source",
            AsyncMock(side_effect=RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError):
            await service.set_ability_bonuses(1, AbilityBonusesUpdate(ability_bonuses=[]))

        assert db.rollbacks == 1
        assert db.commits == 0
        assert purges == []

    async def test_set_ability_bonuses_raises_when_race_missing_inside_the_transaction(self):
        service, db = make_service(RaceAbilityBonusService, existing_by_id={})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        with pytest.raises(RecordNotFoundError):
            await service.set_ability_bonuses(99, data)

        assert service.repository.set_ability_bonuses_calls == []
        assert db.rollbacks == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceSkillService:
    async def test_set_skills_replaces_granted_skills(self, purges):
        race = make_race()
        service, db = make_service(RaceSkillService, existing_by_id={1: race}, skills={1: make_skill()})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[1]))

        assert result.granted_skills[0].id == 1
        assert service.repository.set_skills_calls == [(race.id, [race.granted_skills[0]], False)]
        assert db.commits == 1
        assert purges == [["races"]]

    async def test_set_skills_with_empty_ids_calls_repository_with_none(self):
        race = make_race()
        service, _ = make_service(RaceSkillService, existing_by_id={1: race})

        result = await service.set_skills(1, SkillsUpdate(skill_ids=[]))

        assert result.granted_skills == []
        assert service.repository.set_skills_calls == [(race.id, None, False)]

    async def test_set_skills_raises_when_race_missing(self):
        service, _ = make_service(RaceSkillService, existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_skills(99, SkillsUpdate(skill_ids=[1]))

    async def test_set_skills_rejects_unknown_ids_before_writing(self, purges):
        from app.core.exceptions import RecordIdsInvalidError

        service, _ = make_service(RaceSkillService, existing_by_id={1: make_race()}, skills={})

        with pytest.raises(RecordIdsInvalidError):
            await service.set_skills(1, SkillsUpdate(skill_ids=[7]))

        assert service.repository.set_skills_calls == []
        assert purges == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceTagService:
    async def test_set_tags_purges_races_and_tag_listings(self, purges):
        race = make_race()
        tag = Tag(id=3, name="Sutrice")
        service, _ = make_service(RaceTagService, existing_by_id={1: race}, tags={3: tag})

        result = await service.set_tags(1, TagsUpdate(tag_ids=[3]))

        assert [item.id for item in result.tags] == [3]
        assert service.repository.set_tags_calls == [(1, [tag], False)]
        assert purges == [["races", "tags"]]

    async def test_set_tags_raises_when_race_missing(self):
        service, _ = make_service(RaceTagService, existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_tags(99, TagsUpdate(tag_ids=[1]))


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceFeatureService:
    async def test_list_features_reads_race_source_features(self):
        db = FakeAsyncSession()
        service = RaceFeatureService(db)
        service.repository = FakeRaceRepository(db, existing_by_id={1: make_race()})
        calls = []

        async def list_for_source(source_type, source_id):
            calls.append((source_type, source_id))
            return []

        service._features = SimpleNamespace(list_for_source=list_for_source)

        assert await service.list_features(1) == []
        assert calls == [(FeatureSourceType.RACE, 1)]

    async def test_list_features_raises_when_race_missing(self):
        db = FakeAsyncSession()
        service = RaceFeatureService(db)
        service.repository = FakeRaceRepository(db, existing_by_id={})

        with pytest.raises(RecordNotFoundError) as exc:
            await service.list_features(9)

        assert "Race" in str(exc.value)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceRepository:
    async def test_get_subrace_returns_the_scoped_row(self):
        subrace = make_subrace(id=1, race_id=5)
        session = FakeAsyncSession(scalar_results=[subrace])

        assert await RaceRepository(session).get_subrace(5, 1) is subrace

    async def test_get_subrace_returns_none_when_not_in_that_race(self):
        session = FakeAsyncSession(scalar_results=[None])

        assert await RaceRepository(session).get_subrace(5, 1) is None

    async def test_get_subrace_is_a_bare_select_scoped_by_race_and_id(self):
        class Recording(FakeAsyncSession):
            async def scalar(self, stmt):
                self.statement = stmt
                return None

        session = Recording()

        await RaceRepository(session).get_subrace(5, 1)

        sql = str(session.statement)
        assert "subraces.race_id" in sql
        assert "subraces.id" in sql
        assert "JOIN" not in sql

    async def test_is_in_use_checks_race_and_its_subraces_in_one_query(self):
        class Recording(FakeAsyncSession):
            async def scalar(self, stmt):
                self.statement = stmt
                return 1

        session = Recording()

        assert await RaceRepository(session).is_in_use(5) is True

        sql = str(session.statement)
        assert "characters.race_id" in sql
        assert "characters.subrace_id IN" in sql

    async def test_is_in_use_false_when_nothing_references(self):
        assert await RaceRepository(FakeAsyncSession(scalar_results=[None])).is_in_use(5) is False

    async def test_list_subrace_ids(self):
        session = FakeAsyncSession(execute_results=[FakeResult([4, 5])])

        assert await RaceRepository(session).list_subrace_ids(1) == [4, 5]

    async def test_set_ability_bonuses_replaces_child_rows_and_commits(self):
        session = FakeAsyncSession()

        await RaceRepository(session).set_ability_bonuses(
            1, [{"ability": AbilityScore.DEX, "bonus": 2}, {"ability": AbilityScore.INT, "bonus": 1}]
        )

        assert len(session.added) == 2
        assert all(isinstance(row, RaceAbilityBonus) for row in session.added)
        assert session.added[0].ability == AbilityScore.DEX
        assert session.commits == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRaceSkillsRepository:
    async def test_set_skills_replaces_association_and_commits(self):
        session = FakeAsyncSession()

        await RaceSkillsRepository(session).set_skills(1, [make_skill(), make_skill(id=2, name="Acrobatics")])

        assert len(session.executes) == 2
        assert session.commits == 1

    async def test_set_skills_with_empty_list_and_no_commit_flushes(self):
        session = FakeAsyncSession()

        await RaceSkillsRepository(session).set_skills(1, [], commit=False)

        assert session.flushes == 1
        assert session.commits == 0

    async def test_set_skills_with_none_clears_association(self):
        session = FakeAsyncSession()

        await RaceSkillsRepository(session).set_skills(1, None)

        assert session.commits == 1

    async def test_get_skills_by_ids_looks_up_rows(self):
        skill = make_skill()
        session = FakeAsyncSession(execute_results=[FakeResult([skill])])

        assert await RaceSkillsRepository(session).get_skills_by_ids([1]) == [skill]
        assert len(session.executes) == 1


@pytest.mark.unit
class TestRaceFeatureStaticEffectGroupsSerialization:
    """Regression: RaceRepository eager-loads Feature.static_groups without crashing."""

    def test_race_with_feature_static_groups_serializes_correctly(self):
        from app.features.races.crud.schemas import RaceResponse

        feature_with_effects = SimpleNamespace(
            id=10,
            name="Darkvision",
            description="Superior vision in dim light.",
            level=None,
            static_groups=[
                {
                    "effect_type": "ability",
                    "items": [SimpleNamespace(ability=AbilityScore.STR, amount=2, new_cap=None)],
                },
            ],
        )
        race = SimpleNamespace(
            id=1,
            name="Elf",
            size=RaceSize.MEDIUM,
            speed=30,
            description="An elf.",
            image_url=None,
            ability_bonuses=[],
            granted_skills=[],
            features=[feature_with_effects],
            subraces=[],
        )

        response = RaceResponse.model_validate(race)

        assert len(response.features) == 1
        assert response.features[0].static_groups[0].items[0].ability == AbilityScore.STR
        assert response.features[0].static_groups[0].items[0].amount == 2

    def test_race_with_empty_feature_static_groups_serializes_empty_list(self):
        from app.features.races.crud.schemas import RaceResponse

        feature_no_effects = SimpleNamespace(
            id=11, name="Keen Senses", description="Proficiency in Perception.", level=None, static_groups=[]
        )
        race = SimpleNamespace(
            id=2,
            name="Human",
            size=RaceSize.MEDIUM,
            speed=30,
            description="A human.",
            image_url=None,
            ability_bonuses=[],
            granted_skills=[],
            features=[feature_no_effects],
            subraces=[],
        )

        assert RaceResponse.model_validate(race).features[0].static_groups == []
