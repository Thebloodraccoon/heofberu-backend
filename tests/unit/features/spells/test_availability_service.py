"""
Unit tests for SpellAvailabilityService and create_spell availability seeding.

Covers the full-replace public writes (``set_classes``/``set_subclasses``/
``set_races``/``set_subraces``, empty list = unrestricted) running in one
transaction with the cache purge after the commit, and the create flow that
seeds a new spell's availability in the same transaction as the spell row.
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
from app.features.spells.crud.repository import availability_dimension
from app.features.spells.crud.schemas import SpellCreate
from app.features.spells.crud.service import SpellCrudService
from app.models.spells.spell_model import Spell
from tests.unit.fakes import FakeAsyncSession, FakeRepository

DIMENSIONS = (
    ("classes", "available_classes", ClassAvailabilityUpdate, "class_ids"),
    ("subclasses", "available_subclasses", SubclassAvailabilityUpdate, "subclass_ids"),
    ("races", "available_races", RaceAvailabilityUpdate, "race_ids"),
    ("subraces", "available_subraces", SubraceAvailabilityUpdate, "subrace_ids"),
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
        else:
            await self.db.flush()
        return row

    async def get_dimension_members(self, dimension, ids):
        self.lookup_calls.append((dimension.field, ids))
        known = self.children.get(dimension.field, {})
        return [known[item_id] for item_id in ids if item_id in known]

    async def set_availability(self, spell_id, dimension, child_ids, *, commit=True):
        self.set_calls.append((dimension.field, spell_id, child_ids, commit))
        spell = self._rows.get(spell_id)
        if spell is not None:
            known = self.children.get(dimension.field, {})
            setattr(spell, dimension.field, [known.get(child_id, make_child(id=child_id)) for child_id in child_ids])
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()


@pytest.fixture
def purged(monkeypatch) -> AsyncMock:
    """Namespace purges (both the BaseService path and the transaction helper) instead of Redis."""

    mock = AsyncMock()
    monkeypatch.setattr("app.core.base.service.invalidate", mock)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", mock)
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
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestSpellAvailabilityService:
    @pytest.mark.parametrize(("dimension", "field", "schema", "id_field"), DIMENSIONS)
    async def test_set_dimension_replaces_rows_in_one_transaction_and_purges_after_commit(
        self, dimension, field, schema, id_field, purged
    ):
        child = make_child()
        service, db = make_availability_service(existing_by_id={1: make_spell()}, children={field: {5: child}})
        commits_seen = []
        purged.side_effect = lambda namespace: commits_seen.append(db.commits)

        result = await getattr(service, f"set_{dimension}")(1, schema(**{id_field: [5]}))

        assert service.repository.set_calls == [(field, 1, [5], False)]
        assert purged.await_args_list[0].args == ("spells",)
        assert commits_seen == [1]
        assert db.commits == 1
        assert getattr(result, field)[0].id == 5

    @pytest.mark.parametrize(("dimension", "field", "schema", "id_field"), DIMENSIONS)
    async def test_set_dimension_with_empty_list_clears_without_lookup(
        self, dimension, field, schema, id_field, purged
    ):
        service, _ = make_availability_service(existing_by_id={1: make_spell()})

        result = await getattr(service, f"set_{dimension}")(1, schema(**{id_field: []}))

        assert service.repository.set_calls == [(field, 1, [], False)]
        assert service.repository.lookup_calls == []
        assert purged.await_count == 1
        assert getattr(result, field) == []

    async def test_repeated_ids_are_collapsed_before_the_write(self, purged):
        service, _ = make_availability_service(
            existing_by_id={1: make_spell()}, children={"available_classes": {5: make_child()}}
        )

        await service.set_classes(1, ClassAvailabilityUpdate(class_ids=[5, 5, 5]))

        assert service.repository.lookup_calls == [("available_classes", [5])]
        assert service.repository.set_calls == [("available_classes", 1, [5], False)]

    async def test_set_classes_raises_when_spell_missing(self, purged):
        service, _ = make_availability_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.set_classes(99, ClassAvailabilityUpdate(class_ids=[5]))

        assert service.repository.set_calls == []
        assert purged.await_count == 0

    async def test_set_classes_raises_when_class_ids_unresolvable(self, purged):
        service, db = make_availability_service(existing_by_id={1: make_spell()})

        with pytest.raises(RecordIdsInvalidError):
            await service.set_classes(1, ClassAvailabilityUpdate(class_ids=[404]))

        assert service.repository.set_calls == []
        assert db.commits == 0
        assert purged.await_count == 0

    async def test_failed_write_rolls_back_and_purges_nothing(self, purged):
        service, db = make_availability_service(
            existing_by_id={1: make_spell()}, children={"available_classes": {5: make_child()}}
        )

        async def boom(*args, **kwargs):
            raise RuntimeError("insert failed")

        service.repository.set_availability = boom

        with pytest.raises(RuntimeError):
            await service.set_classes(1, ClassAvailabilityUpdate(class_ids=[5]))

        assert db.rollbacks == 1
        assert db.commits == 0
        assert purged.await_count == 0


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

    async def test_create_spell_seeds_availability_in_same_transaction(self, purged):
        service, db = make_crud_service(
            children={"available_classes": {5: make_child()}, "available_races": {9: make_child(id=9)}}
        )
        commits_seen = []
        purged.side_effect = lambda namespace: commits_seen.append(db.commits)

        result = await service.create_spell(self._spell_data(available_classes=[5], available_races=[9]))

        assert service.repository.set_calls == [
            ("available_classes", 1, [5], False),
            ("available_races", 1, [9], False),
        ]
        assert db.commits == 1
        assert commits_seen == [1]
        assert result.available_classes[0].id == 5
        assert result.available_races[0].id == 9

    async def test_create_spell_without_availability_skips_seeding(self, purged):
        service, db = make_crud_service()

        result = await service.create_spell(self._spell_data())

        assert service.repository.set_calls == []
        assert db.commits == 1
        assert result.id == 1

    async def test_create_spell_with_unknown_class_id_is_rejected_before_any_write(self, purged):
        service, db = make_crud_service(children={})

        with pytest.raises(RecordIdsInvalidError):
            await service.create_spell(self._spell_data(available_classes=[404]))

        assert service.repository.created == []
        assert db.commits == 0

    async def test_create_spell_collapses_repeated_availability_ids(self, purged):
        service, _ = make_crud_service(children={"available_classes": {5: make_child()}})

        await service.create_spell(self._spell_data(available_classes=[5, 5]))

        assert service.repository.lookup_calls == [("available_classes", [5])]

    async def test_create_spell_rolls_back_when_persist_fails(self, purged):
        service, db = make_crud_service()

        class Boom(Exception):
            pass

        async def boom(*args, **kwargs):
            raise Boom()

        service.repository.create = boom

        with pytest.raises(Boom):
            await service.create_spell(self._spell_data())

        assert db.rollbacks == 1
        assert purged.await_count == 0


@pytest.mark.unit
class TestAvailabilityDimensions:
    def test_each_dimension_maps_field_to_its_association_column(self):
        mapping = {field: availability_dimension(field).child_fk for _, field, _, _ in DIMENSIONS}
        assert mapping == {
            "available_classes": "class_id",
            "available_subclasses": "subclass_id",
            "available_races": "race_id",
            "available_subraces": "subrace_id",
        }
