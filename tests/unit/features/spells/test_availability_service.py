"""
Unit tests for SpellAvailabilityService and create_spell availability seeding.

Covers the full-replace public writes (``set_classes``/``set_subclasses``/
``set_races``/``set_subraces``, empty list = unrestricted), the
``commit=False`` ``set_*_for_spell`` variants shared with ``create_spell``,
and the crud-service composition that seeds a new spell's availability in
the same transaction as the spell row with the cache purge after commit.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import SpellCastTime, SpellDuration, SpellLevel, SpellRangeType, SpellSchool
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.features.spells.availability.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SubclassAvailabilityUpdate,
    SubraceAvailabilityUpdate,
)
from app.features.spells.availability.service import SpellAvailabilityService
from app.features.spells.crud.schemas import SpellCreate
from app.features.spells.crud.service import SpellCrudService
from app.models.spell_model import Spell
from tests.unit.fakes import FakeAsyncSession, FakeRepository

DIMENSIONS = (
    ("classes", ClassAvailabilityUpdate, "class_ids"),
    ("subclasses", SubclassAvailabilityUpdate, "subclass_ids"),
    ("races", RaceAvailabilityUpdate, "race_ids"),
    ("subraces", SubraceAvailabilityUpdate, "subrace_ids"),
)


def make_spell(**overrides) -> Spell:
    base = {
        "id": 1,
        "name": "Magic Missile",
        "school": SpellSchool.EVOCATION,
        "level": SpellLevel.LEVEL_1,
        "cast_time": SpellCastTime.ACTION,
        "range_type": SpellRangeType.SELF,
        "components": [],
        "is_material_consumed": False,
        "is_ritual": False,
        "is_concentration": False,
        "duration": SpellDuration.INSTANTANEOUS,
        "description": "",
        "available_classes": [],
        "available_subclasses": [],
        "available_races": [],
        "available_subraces": [],
    }
    base.update(overrides)
    payload = {key: value for key, value in base.items() if key != "id"}
    spell = Spell(**payload)
    spell.id = base["id"]
    return spell


def make_child(**overrides) -> SimpleNamespace:
    base = {"id": 5, "name": "Wizard"}
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeSpellRepository(FakeRepository):
    """Spell repository stand-in with the availability lookups and writes."""

    def __init__(self, db, existing_by_id=None, children=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Spell)
        self.children = children or {}
        self.lookup_calls = []
        self.set_calls = []

    async def create(self, payload, *, commit=True):
        row = Spell(**payload)
        row.id = self._next_id
        self._next_id += 1
        self._rows[row.id] = row
        self.created.append(row)
        if commit:
            await self.db.commit()
        return row

    async def _lookup(self, dimension, ids):
        self.lookup_calls.append((dimension, ids))
        known = self.children.get(dimension, {})
        return [known[item_id] for item_id in ids if item_id in known]

    async def get_classes_by_ids(self, class_ids):
        return await self._lookup("classes", class_ids)

    async def get_subclasses_by_ids(self, subclass_ids):
        return await self._lookup("subclasses", subclass_ids)

    async def get_races_by_ids(self, race_ids):
        return await self._lookup("races", race_ids)

    async def get_subraces_by_ids(self, subrace_ids):
        return await self._lookup("subraces", subrace_ids)

    async def _set(self, dimension, spell, rows, *, commit):
        self.set_calls.append((dimension, spell, rows, commit))
        setattr(spell, f"available_{dimension}", list(rows))
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def set_classes(self, spell, classes, *, commit=True):
        return await self._set("classes", spell, classes, commit=commit)

    async def set_subclasses(self, spell, subclasses, *, commit=True):
        return await self._set("subclasses", spell, subclasses, commit=commit)

    async def set_races(self, spell, races, *, commit=True):
        return await self._set("races", spell, races, commit=commit)

    async def set_subraces(self, spell, subraces, *, commit=True):
        return await self._set("subraces", spell, subraces, commit=commit)


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    """Stop generic cache invalidation from touching Redis."""
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())


@pytest.fixture
def invalidated(monkeypatch) -> AsyncMock:
    """Capture invalidate_spell_cache calls inside the availability service."""
    mock = AsyncMock()
    monkeypatch.setattr("app.features.spells.availability.service.invalidate_spell_cache", mock)
    return mock


def make_availability_service(existing_by_id=None, children=None):
    db = FakeAsyncSession()
    service = SpellAvailabilityService(db)
    service.repository = FakeSpellRepository(db, existing_by_id=existing_by_id, children=children)
    return service, db


def make_crud_service(existing_by_id=None, children=None):
    db = FakeAsyncSession()
    service = SpellCrudService(db)
    service.repository = FakeSpellRepository(db, existing_by_id=existing_by_id, children=children)
    service._availability = FakeAvailabilityService(db)
    return service, db


class FakeAvailabilityService:
    """Stands in for SpellAvailabilityService inside SpellCrudService."""

    def __init__(self, db):
        self.db = db
        self.calls = []

    async def set_classes_for_spell(self, spell, classes, *, commit=True):
        self.calls.append(("classes", spell, classes, commit))
        spell.available_classes = list(classes)

    async def set_subclasses_for_spell(self, spell, subclasses, *, commit=True):
        self.calls.append(("subclasses", spell, subclasses, commit))
        spell.available_subclasses = list(subclasses)

    async def set_races_for_spell(self, spell, races, *, commit=True):
        self.calls.append(("races", spell, races, commit))
        spell.available_races = list(races)

    async def set_subraces_for_spell(self, spell, subraces, *, commit=True):
        self.calls.append(("subraces", spell, subraces, commit))
        spell.available_subraces = list(subraces)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpellAvailabilityService:
    @pytest.mark.parametrize(("dimension", "schema", "id_field"), DIMENSIONS)
    async def test_set_dimension_replaces_rows_and_invalidates_cache(self, dimension, schema, id_field, invalidated):
        child = make_child()
        service, db = make_availability_service(existing_by_id={1: make_spell()}, children={dimension: {5: child}})
        data = schema(**{id_field: [5]})

        result = await getattr(service, f"set_{dimension}")(1, data)

        assert service.repository.set_calls == [(dimension, service.repository._rows[1], [child], True)]
        assert invalidated.await_count == 1
        assert db.commits == 1
        assert getattr(result, f"available_{dimension}")[0].id == 5

    @pytest.mark.parametrize(("dimension", "schema", "id_field"), DIMENSIONS)
    async def test_set_dimension_with_empty_list_clears_without_lookup(self, dimension, schema, id_field, invalidated):
        service, _ = make_availability_service(existing_by_id={1: make_spell()})
        data = schema(**{id_field: []})

        result = await getattr(service, f"set_{dimension}")(1, data)

        assert service.repository.set_calls == [(dimension, service.repository._rows[1], [], True)]
        assert service.repository.lookup_calls == []
        assert invalidated.await_count == 1
        assert getattr(result, f"available_{dimension}") == []

    async def test_set_classes_raises_when_spell_missing(self, invalidated):
        service, _ = make_availability_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_classes(99, ClassAvailabilityUpdate(class_ids=[5]))

        assert service.repository.set_calls == []
        assert invalidated.await_count == 0

    async def test_set_classes_raises_when_class_ids_unresolvable(self, invalidated):
        service, _ = make_availability_service(existing_by_id={1: make_spell()})

        with pytest.raises(RecordIdsInvalidError):
            await service.set_classes(1, ClassAvailabilityUpdate(class_ids=[404]))

        assert service.repository.set_calls == []
        assert invalidated.await_count == 0

    @pytest.mark.parametrize(("dimension", "schema", "id_field"), DIMENSIONS)
    async def test_set_for_spell_delegates_without_commit_or_invalidation(self, dimension, schema, id_field, invalidated):
        child = make_child()
        spell = make_spell()
        service, db = make_availability_service()

        await getattr(service, f"set_{dimension}_for_spell")(spell, [child], commit=False)

        assert service.repository.set_calls == [(dimension, spell, [child], False)]
        assert db.commits == 0
        assert invalidated.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateSpellSeeding:
    def _spell_data(self, **availability) -> SpellCreate:
        return SpellCreate(
            name="Cure Wounds",
            school=SpellSchool.EVOCATION,
            level=SpellLevel.LEVEL_1,
            cast_time=SpellCastTime.ACTION,
            range_type=SpellRangeType.TOUCH,
            duration=SpellDuration.INSTANTANEOUS,
            description="",
            **availability,
        )

    async def test_create_spell_seeds_availability_in_same_transaction(self, monkeypatch):
        invalidation = AsyncMock()
        monkeypatch.setattr("app.features.spells.crud.service.invalidate_spell_cache", invalidation)
        service, db = make_crud_service(children={"classes": {5: make_child()}, "races": {9: make_child(id=9)}})

        result = await service.create_spell(self._spell_data(available_classes=[5], available_races=[9]))

        assert [call[0] for call in service._availability.calls] == ["classes", "races"]
        assert [call[1].id for call in service._availability.calls] == [1, 1]
        assert all(call[3] is False for call in service._availability.calls)
        assert service._availability.calls[0][2] == [make_child()]
        assert service._availability.calls[1][2] == [make_child(id=9)]
        assert db.commits == 1
        assert invalidation.await_count == 1
        assert result.available_classes[0].id == 5

    async def test_create_spell_without_availability_skips_seeding(self):
        service, db = make_crud_service()

        result = await service.create_spell(self._spell_data())

        assert service._availability.calls == []
        assert db.commits == 1
        assert result.id == 1

    async def test_create_spell_rolls_back_when_persist_fails(self):
        service, db = make_crud_service()

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_spell(self._spell_data())

        assert db.rollbacks == 1
