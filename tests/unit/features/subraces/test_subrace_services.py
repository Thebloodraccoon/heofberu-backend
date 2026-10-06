"""
Unit tests for the subrace services (crud / ability bonuses / tags / features).

The services run on recording fake repositories so the service bodies (which
the HTTP-level integration tests do not trace) are covered directly.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, FeatureSourceType
from app.core.exceptions import RecordNotFoundError
from app.features.shared.catalog.schemas import AbilityBonusesUpdate, AbilityBonusItem
from app.features.shared.tags.schemas import TagsUpdate
from app.features.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.subraces.crud.schemas import SubraceCreate, SubraceUpdate
from app.features.subraces.crud.service import SubraceCrudService
from app.features.subraces.features.service import SubraceFeatureService
from app.features.subraces.tags.service import SubraceTagService
from app.models.races.subrace_association_models import SubraceAbilityBonus
from app.models.races.subrace_model import Subrace
from app.models.tag_model import Tag
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_subrace(**overrides) -> Subrace:
    base = {"id": 1, "race_id": 1, "name": "High Elf", "description": "", "ability_bonuses": [], "tags": []}
    base.update(overrides)
    return Subrace(**base)


class FakeSubraceRepository(FakeRepository):
    """Subrace repository stand-in with the capability methods the services need."""

    def __init__(self, db, existing_by_id=None, race_exists=True, tags=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Subrace)
        self._race_exists = race_exists
        self.tags = tags or {}
        self.set_bonuses_calls = []
        self.list_calls = []
        self.race_checks = []

    async def race_exists(self, race_id: int) -> bool:
        self.race_checks.append(race_id)
        return self._race_exists

    async def create(self, payload):
        row = Subrace(**payload, ability_bonuses=[], tags=[])
        row.id = self._next_id
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        return row

    async def list_for_race(self, race_id: int):
        self.list_calls.append(race_id)
        return [subrace for subrace in self._rows.values() if subrace.race_id == race_id]

    async def set_ability_bonuses(self, subrace_id: int, bonuses: list[dict]) -> None:
        self.set_bonuses_calls.append((subrace_id, bonuses))
        subrace = self._rows.get(subrace_id)
        if subrace is not None:
            subrace.ability_bonuses = [
                SubraceAbilityBonus(subrace_id=subrace_id, ability=bonus["ability"], bonus=bonus["bonus"])
                for bonus in bonuses
            ]

    async def set_tags(self, subrace_id: int, tags) -> None:
        self._rows[subrace_id].tags = list(tags or [])

    async def get_tags_by_ids(self, tag_ids):
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
    monkeypatch.setattr("app.features.subraces.cache.invalidate_many", fake_invalidate_many)
    return calls


@pytest.fixture(autouse=True)
def no_reconcile(monkeypatch):
    monkeypatch.setattr(
        "app.features.characters.progression.source_bonuses.reconcile_characters_for_source", AsyncMock()
    )


def make_crud_service(existing_by_id=None, race_exists=True, storage=None):
    db = FakeAsyncSession()
    service = SubraceCrudService(db, storage)
    service.repository = FakeSubraceRepository(db, existing_by_id=existing_by_id, race_exists=race_exists)
    return service, db


def make_service(cls, existing_by_id=None, **repository_kwargs):
    db = FakeAsyncSession()
    service = cls(db)
    service.repository = FakeSubraceRepository(db, existing_by_id=existing_by_id, **repository_kwargs)
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

    async def test_get_by_id_builds_the_response_from_one_load(self):
        subrace = make_subrace(ability_bonuses=[SubraceAbilityBonus(subrace_id=1, ability=AbilityScore.DEX, bonus=2)])
        service, _ = make_crud_service(existing_by_id={1: subrace})
        service.repository.get_by_id = AsyncMock(return_value=subrace)

        result = await service.get_by_id(1)

        assert result.id == 1
        assert result.ability_bonuses[0].ability == AbilityScore.DEX
        service.repository.get_by_id.assert_awaited_once_with(1)

    async def test_get_by_id_raises_when_subrace_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_by_id(99)

    async def test_create_subrace_checks_the_race_and_purges_races(self, purges):
        service, db = make_crud_service()

        result = await service.create_subrace(SubraceCreate(name="Drow", race_id=1, description="Underdark elf"))

        assert (result.id, result.race_id, result.name) == (1, 1, "Drow")
        assert service.repository.race_checks == [1]
        assert db.commits == 1
        assert purges == [["races", "spells"]]

    async def test_create_subrace_raises_when_race_missing(self, purges):
        service, _ = make_crud_service(race_exists=False)

        with pytest.raises(RecordNotFoundError):
            await service.create_subrace(SubraceCreate(name="Drow", race_id=99))

        assert purges == []

    async def test_update_subrace_purges_races(self, purges):
        subrace = make_subrace(id=1)
        service, db = make_crud_service(existing_by_id={1: subrace})

        result = await service.update(1, SubraceUpdate(name="Wood Elf"))

        assert result.name == "Wood Elf"
        assert subrace.name == "Wood Elf"
        assert db.commits >= 1
        assert purges == [["races", "spells"]]

    async def test_update_subrace_raises_when_subrace_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.update(1, SubraceUpdate(name="Wood Elf"))

    async def test_delete_subrace_purges_cascade_namespaces_and_drops_image(self, purges):
        subrace = make_subrace(id=1)
        storage = FakeStorage()
        service, _ = make_crud_service(existing_by_id={1: subrace}, storage=storage)

        assert await service.delete(1) is True

        assert service.repository.deleted == [subrace]
        assert purges == [["races", "subrace_features", "features", "spells"]]
        assert storage.deleted == [("subraces", 1)]

    async def test_delete_blocked_subrace_keeps_cache_and_image(self, purges):
        storage = FakeStorage()
        service, _ = make_crud_service(existing_by_id={1: make_subrace()}, storage=storage)

        async def in_use(subrace):
            raise RuntimeError("in use")

        service.repository.delete = in_use

        with pytest.raises(RuntimeError):
            await service.delete(1)

        assert purges == []
        assert storage.deleted == []

    async def test_delete_subrace_raises_when_subrace_missing(self):
        service, _ = make_crud_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.delete(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceAbilityBonusService:
    async def test_set_ability_bonuses_replaces_reconciles_and_purges_races(self, purges):
        from app.features.characters.progression import source_bonuses as module

        service, db = make_service(SubraceAbilityBonusService, existing_by_id={1: make_subrace(id=1)})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        result = await service.set_ability_bonuses(1, data)

        assert result.ability_bonuses[0].ability == AbilityScore.INT
        assert service.repository.set_bonuses_calls == [(1, [{"ability": AbilityScore.INT, "bonus": 1}])]
        assert db.commits == 1
        module.reconcile_characters_for_source.assert_awaited_once_with(db, FeatureSourceType.SUBRACE, 1)
        assert purges == [["races"]]

    async def test_set_ability_bonuses_raises_when_subrace_missing(self, purges):
        service, db = make_service(SubraceAbilityBonusService, existing_by_id={})
        data = AbilityBonusesUpdate(ability_bonuses=[AbilityBonusItem(ability=AbilityScore.INT, bonus=1)])

        with pytest.raises(RecordNotFoundError):
            await service.set_ability_bonuses(99, data)

        assert db.rollbacks == 1
        assert purges == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceTagService:
    async def test_set_tags_purges_races_and_tag_listings(self, purges):
        tag = Tag(id=3, name="Sutrice")
        service, _ = make_service(SubraceTagService, existing_by_id={1: make_subrace()}, tags={3: tag})

        result = await service.set_tags(1, TagsUpdate(tag_ids=[3]))

        assert [item.id for item in result.tags] == [3]
        assert purges == [["races", "tags"]]

    async def test_set_tags_raises_when_subrace_missing(self):
        service, _ = make_service(SubraceTagService, existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_tags(99, TagsUpdate(tag_ids=[1]))


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceFeatureService:
    async def test_list_features_reads_subrace_source_features(self):
        db = FakeAsyncSession()
        service = SubraceFeatureService(db)
        service.repository = FakeSubraceRepository(db, existing_by_id={1: make_subrace()})
        calls = []

        async def list_for_source(source_type, source_id):
            calls.append((source_type, source_id))
            return []

        service._features = SimpleNamespace(list_for_source=list_for_source)

        assert await service.list_features(1) == []
        assert calls == [(FeatureSourceType.SUBRACE, 1)]

    async def test_list_features_raises_when_subrace_missing(self):
        db = FakeAsyncSession()
        service = SubraceFeatureService(db)
        service.repository = FakeSubraceRepository(db, existing_by_id={})

        with pytest.raises(RecordNotFoundError) as exc:
            await service.list_features(99)

        assert "Subrace" in str(exc.value)
