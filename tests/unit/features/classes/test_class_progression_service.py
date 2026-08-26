"""
Unit tests for ClassProgressionService: the per-level spell-slot full
replace (including the CANTRIP known-cantrips row), class_level validation,
and the 1-20 progression-table composition.

The repository is faked so the tests trace only the service logic; two
repository-level tests cover ``set_spell_slots``/``get_spell_slot_progression``
against the shared ``replace_child_rows`` machinery.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import DiceType, SpellLevel
from app.core.exceptions import RecordNotFoundError
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.exceptions import InvalidClassLevelException
from app.features.classes.progression.service import ClassProgressionService
from app.features.classes.schemas import SpellSlotEntry, SpellSlotProgressionUpdate
from app.models.class_model import Class
from app.models.class_spell_slot_progression_model import ClassSpellSlotProgression
from tests.unit.fakes import FakeAsyncSession, FakeRepository, FakeResult


def make_class_row(**overrides) -> SimpleNamespace:
    base = {
        "id": 1,
        "name": "Wizard",
        "hit_dice": DiceType.D6,
        "skill_choice_count": 2,
        "spellcasting_ability": None,
        "description": "",
        "saving_throws": [],
        "armor_proficiencies": [],
        "weapon_proficiencies": [],
        "available_skills": [],
        "starting_items": [],
        "spell_slot_progression": [],
        "subclasses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_slot_row(class_level: int, spell_level: SpellLevel, slots: int) -> SimpleNamespace:
    return SimpleNamespace(class_level=class_level, spell_level=spell_level, slots=slots)


class FakeProgressionRepository(FakeRepository):
    """Class repository stand-in with the slot write and progression read."""

    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Class)
        self.slot_calls = []
        self.progression_features = []

    async def set_spell_slots(self, character_class, class_level, slots_by_spell_level, *, commit=True):
        self.slot_calls.append((character_class, class_level, slots_by_spell_level, commit))
        return character_class

    async def get_progression_features(self, class_id):
        return self.progression_features


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())
    monkeypatch.setattr("app.features.classes.progression.service.invalidate_class_cache", AsyncMock())


@pytest.fixture
def invalidated(monkeypatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr("app.features.classes.progression.service.invalidate_class_cache", mock)
    return mock


def make_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = ClassProgressionService(db)
    service.repository = FakeProgressionRepository(db, existing_by_id=existing_by_id)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestSetSpellSlots:
    async def test_set_spell_slots_replaces_only_that_class_level(self, invalidated):
        character_class = make_class_row()
        service, _ = make_service(existing_by_id={1: character_class})
        data = SpellSlotProgressionUpdate(
            slots=[
                SpellSlotEntry(spell_level=SpellLevel.CANTRIP, slots=2),
                SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=4),
            ]
        )

        result = await service.set_spell_slots(1, 1, data)

        assert result.id == 1
        assert service.repository.slot_calls == [(character_class, 1, {"CANTRIP": 2, "LEVEL_1": 4}, True)]
        assert invalidated.await_count == 1

    async def test_cantrip_is_a_valid_slot_row_for_the_known_cantrip_cap(self, invalidated):
        character_class = make_class_row()
        service, _ = make_service(existing_by_id={1: character_class})
        data = SpellSlotProgressionUpdate(slots=[SpellSlotEntry(spell_level=SpellLevel.CANTRIP, slots=3)])

        await service.set_spell_slots(1, 1, data)

        assert service.repository.slot_calls == [(character_class, 1, {"CANTRIP": 3}, True)]

    @pytest.mark.parametrize("class_level", [0, 21, -1])
    async def test_set_spell_slots_rejects_class_level_outside_1_20(self, class_level, invalidated):
        service, _ = make_service(existing_by_id={1: make_class_row()})
        data = SpellSlotProgressionUpdate(slots=[SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=2)])

        with pytest.raises(InvalidClassLevelException) as exc_info:
            await service.set_spell_slots(1, class_level, data)

        assert exc_info.value.class_level == class_level
        assert service.repository.slot_calls == []
        assert invalidated.await_count == 0

    async def test_set_spell_slots_raises_when_class_missing(self, invalidated):
        service, _ = make_service(existing_by_id={})
        data = SpellSlotProgressionUpdate(slots=[SpellSlotEntry(spell_level=SpellLevel.LEVEL_1, slots=2)])

        with pytest.raises(RecordNotFoundError):
            await service.set_spell_slots(99, 1, data)

        assert service.repository.slot_calls == []
        assert invalidated.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetProgression:
    async def test_get_progression_builds_twenty_rows_with_slot_indexing(self):
        character_class = make_class_row(
            spell_slot_progression=[
                make_slot_row(1, SpellLevel.CANTRIP, 2),
                make_slot_row(1, SpellLevel.LEVEL_1, 2),
                make_slot_row(5, SpellLevel.LEVEL_3, 2),
            ]
        )
        service, db = make_service(existing_by_id={1: character_class})

        result = await service.get_progression(1)

        assert result.class_id == 1
        assert result.class_name == "Wizard"
        assert len(result.rows) == 20
        assert result.rows[0].spell_slots == {"CANTRIP": 2, "LEVEL_1": 2}
        assert result.rows[0].proficiency_bonus == 2
        assert result.rows[4].spell_slots == {"LEVEL_3": 2}
        assert result.rows[4].proficiency_bonus == 3
        assert result.rows[19].spell_slots == {}
        assert all(row.class_features == [] and row.subclass_features == [] for row in result.rows)
        assert db.commits == 0

    async def test_get_progression_raises_when_class_missing(self):
        service, _ = make_service(existing_by_id={})

        with pytest.raises(RecordNotFoundError):
            await service.get_progression(99)


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassRepositorySlotHelpers:
    async def test_set_spell_slots_scopes_delete_to_class_level_and_commits(self):
        session = FakeAsyncSession()
        repository = ClassRepository(session)
        character_class = make_class_row()

        result = await repository.set_spell_slots(character_class, 1, {"CANTRIP": 2})

        assert result is character_class
        assert len(session.added) == 1
        added = session.added[0]
        assert isinstance(added, ClassSpellSlotProgression)
        assert added.class_id == 1
        assert added.class_level == 1
        assert added.spell_level == SpellLevel.CANTRIP
        assert added.slots == 2
        assert len(session.executes) == 1
        assert session.commits == 1

    async def test_set_spell_slots_with_commit_false_flushes_instead(self):
        session = FakeAsyncSession()
        repository = ClassRepository(session)

        await repository.set_spell_slots(make_class_row(), 2, {"LEVEL_1": 2}, commit=False)

        assert session.flushes == 1
        assert session.commits == 0

    async def test_get_spell_slot_progression_maps_rows_to_dict(self):
        rows = [
            ClassSpellSlotProgression(class_id=1, class_level=1, spell_level=SpellLevel.CANTRIP, slots=2),
            ClassSpellSlotProgression(class_id=1, class_level=1, spell_level=SpellLevel.LEVEL_1, slots=2),
        ]
        session = FakeAsyncSession(execute_results=[FakeResult(rows)])
        repository = ClassRepository(session)

        result = await repository.get_spell_slot_progression(1, 1)

        assert result == {"CANTRIP": 2, "LEVEL_1": 2}

    async def test_get_spell_slot_progression_empty_when_no_rows(self):
        session = FakeAsyncSession(execute_results=[FakeResult([])])
        repository = ClassRepository(session)

        assert await repository.get_spell_slot_progression(1, 7) == {}
