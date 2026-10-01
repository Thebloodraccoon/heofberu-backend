"""
Unit tests for ClassProgressionService: the per-level spell-slot full replace
(including the CANTRIP known-cantrips row) and the 1-20 progression table
composition; plus the repository's spell-slot helpers.
"""

from types import SimpleNamespace

import pytest

from app.constants import SpellLevel
from app.core.exceptions import RecordNotFoundError
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.progression.schemas import (
    ProgressionSubclassFeature,
    SpellSlotEntry,
    SpellSlotProgressionUpdate,
)
from app.features.classes.progression.service import ClassProgressionService
from app.models.classes.class_spell_slot_progression_model import ClassSpellSlotProgression
from tests.unit.fakes import FakeAsyncSession, FakeResult
from tests.unit.features.classes.helpers import FakeClassRepository, make_class_row, purged_namespaces


def make_slot_row(class_level: int, spell_level: SpellLevel, slots: int) -> SimpleNamespace:
    return SimpleNamespace(class_level=class_level, spell_level=spell_level, slots=slots)


def make_feature(
    feature_id: int, level: int | None, subclass_id: int | None = None, name: str = "F"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=feature_id,
        name=name,
        description="",
        level=level,
        subclass_id=subclass_id,
        choice_groups=[],
        static_groups=[],
        has_static_effects=False,
        has_choices=False,
        effects_summary="",
    )


def make_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = ClassProgressionService(db)
    service.repository = FakeClassRepository(db, existing_by_id=existing_by_id)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetSpellSlots:
    async def test_replaces_only_that_class_level_and_purges_class_reads(self, purged):
        service, _ = make_service(existing_by_id={1: make_class_row()})
        data = SpellSlotProgressionUpdate(
            slots=[
                SpellSlotEntry(spell_level=SpellLevel.CANTRIP, slots=2),
                SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=4),
            ]
        )

        result = await service.set_spell_slots(1, 3, data)

        assert result.id == 1
        assert service.repository.slot_calls == [(1, 3, {"CANTRIP": 2, "LEVEL_1": 4}, True)]
        assert purged_namespaces(purged) == ["classes"]

    async def test_cantrip_is_a_valid_slot_row_for_the_known_cantrip_cap(self, purged):
        service, _ = make_service(existing_by_id={1: make_class_row()})
        data = SpellSlotProgressionUpdate(slots=[SpellSlotEntry(spell_level=SpellLevel.CANTRIP, slots=3)])

        await service.set_spell_slots(1, 1, data)

        assert service.repository.slot_calls == [(1, 1, {"CANTRIP": 3}, True)]

    async def test_raises_when_class_missing(self, purged):
        service, _ = make_service(existing_by_id={})
        data = SpellSlotProgressionUpdate(slots=[SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=2)])

        with pytest.raises(RecordNotFoundError):
            await service.set_spell_slots(99, 1, data)

        assert service.repository.slot_calls == []
        assert purged.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetProgression:
    async def test_builds_twenty_rows_with_slot_indexing(self):
        service, db = make_service(existing_by_id={1: make_class_row(name="Wizard")})
        service.repository.slot_rows = [
            make_slot_row(1, SpellLevel.CANTRIP, 2),
            make_slot_row(1, SpellLevel.LEVEL_1, 2),
            make_slot_row(5, SpellLevel.LEVEL_3, 2),
        ]

        result = await service.get_progression(1)

        assert (result.class_id, result.class_name) == (1, "Wizard")
        assert len(result.rows) == 20
        assert result.rows[0].spell_slots == {"CANTRIP": 2, "LEVEL_1": 2}
        assert result.rows[0].proficiency_bonus == 2
        assert result.rows[4].spell_slots == {"LEVEL_3": 2}
        assert result.rows[4].proficiency_bonus == 3
        assert result.rows[19].spell_slots == {}
        assert all(row.class_features == [] and row.subclass_features == [] for row in result.rows)
        assert db.commits == 0

    async def test_places_class_and_subclass_features_on_their_levels(self):
        service, _ = make_service(existing_by_id={1: make_class_row()})
        service.repository.progression_features = [
            make_feature(1, 1, name="Second Wind"),
            make_feature(2, 3, subclass_id=5, name="Improved Critical"),
            make_feature(3, 3, subclass_id=6, name="Combat Superiority"),
            make_feature(4, None, name="Orphan"),
        ]

        result = await service.get_progression(1)

        assert [f.name for f in result.rows[0].class_features] == ["Second Wind"]
        level_three = result.rows[2]
        assert [(f.name, f.subclass_id) for f in level_three.subclass_features] == [
            ("Improved Critical", 5),
            ("Combat Superiority", 6),
        ]
        assert all(isinstance(f, ProgressionSubclassFeature) for f in level_three.subclass_features)
        assert level_three.class_features == []
        assert sum(len(row.class_features) for row in result.rows) == 1

    async def test_raises_when_class_missing(self):
        service, _ = make_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_progression(99)


@pytest.mark.unit
class TestSlotEntryValidation:
    def test_negative_slots_rejected(self):
        with pytest.raises(ValueError):
            SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=-1)

    def test_absurd_slot_count_rejected(self):
        with pytest.raises(ValueError):
            SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=1000)


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassRepositorySlotHelpers:
    async def test_set_spell_slots_scopes_delete_to_class_level_and_commits(self):
        session = FakeAsyncSession()
        repository = ClassRepository(session)

        await repository.set_spell_slots(1, 1, {"CANTRIP": 2})

        assert len(session.added) == 1
        added = session.added[0]
        assert isinstance(added, ClassSpellSlotProgression)
        assert (added.class_id, added.class_level, added.spell_level, added.slots) == (1, 1, SpellLevel.CANTRIP, 2)
        assert len(session.executes) == 1
        assert session.commits == 1

    async def test_set_spell_slots_with_commit_false_flushes_instead(self):
        session = FakeAsyncSession()
        repository = ClassRepository(session)

        await repository.set_spell_slots(1, 2, {"LEVEL_1": 2}, commit=False)

        assert session.flushes == 1
        assert session.commits == 0

    async def test_get_spell_slot_progression_maps_rows_to_dict(self):
        rows = [
            ClassSpellSlotProgression(class_id=1, class_level=1, spell_level=SpellLevel.CANTRIP, slots=2),
            ClassSpellSlotProgression(class_id=1, class_level=1, spell_level=SpellLevel.LEVEL_1, slots=2),
        ]
        repository = ClassRepository(FakeAsyncSession(execute_results=[FakeResult(rows)]))

        assert await repository.get_spell_slot_progression(1, 1) == {"CANTRIP": 2, "LEVEL_1": 2}

    async def test_get_spell_slot_progression_empty_when_no_rows(self):
        repository = ClassRepository(FakeAsyncSession(execute_results=[FakeResult([])]))

        assert await repository.get_spell_slot_progression(1, 7) == {}
