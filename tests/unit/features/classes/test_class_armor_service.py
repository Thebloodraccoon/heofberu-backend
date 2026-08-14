"""Unit tests for ClassArmorService (set_armor_proficiencies)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import ArmorProficiency, DiceType
from app.core.exceptions import RecordNotFoundError
from app.features.classes.armor.service import ClassArmorService
from app.features.classes.schemas import ArmorProficienciesUpdate
from app.models.class_model import Class
from tests.unit.fakes import FakeAsyncSession, FakeRepository


def make_class_row(**overrides) -> SimpleNamespace:
    base = {
        "id": 1,
        "name": "Fighter",
        "hit_dice": DiceType.D10,
        "skill_choice_count": 2,
        "spellcasting_ability": None,
        "description": "",
        "created_by_id": None,
        "primary_abilities": [],
        "saving_throws": [],
        "armor_proficiencies": [],
        "available_skills": [],
        "starting_items": [],
        "spell_slot_progression": [],
        "subclasses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeClassRepository(FakeRepository):
    """Class repository stand-in with the armor-proficiency write."""

    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Class)
        self.armor_calls = []

    async def set_armor_proficiencies(self, character_class, armor_types, *, commit=True):
        self.armor_calls.append((character_class, armor_types, commit))
        setattr(
            character_class,
            "armor_proficiencies",
            [SimpleNamespace(armor_type=armor_type) for armor_type in armor_types],
        )
        if commit:
            await self.db.commit()
        return character_class


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())
    monkeypatch.setattr("app.features.classes.armor.service.invalidate_class_cache", AsyncMock())


def make_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = ClassArmorService(db)
    service.repository = FakeClassRepository(db, existing_by_id=existing_by_id)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassArmorService:
    async def test_set_armor_proficiencies_replaces_and_returns_class(self):
        class_row = make_class_row()
        service, db = make_service(existing_by_id={1: class_row})
        data = ArmorProficienciesUpdate(armor_proficiencies=[ArmorProficiency.LIGHT, ArmorProficiency.HEAVY])

        result = await service.set_armor_proficiencies(1, data)

        assert result.id == 1
        assert service.repository.armor_calls[0][0] is class_row
        assert service.repository.armor_calls[0][1] == [ArmorProficiency.LIGHT, ArmorProficiency.HEAVY]
        assert service.repository.armor_calls[0][2] is True
        assert db.commits == 1

    async def test_set_armor_proficiencies_raises_when_class_missing(self):
        service, _ = make_service(existing_by_id={})
        data = ArmorProficienciesUpdate(armor_proficiencies=[ArmorProficiency.LIGHT])

        with pytest.raises(RecordNotFoundError):
            await service.set_armor_proficiencies(99, data)

    async def test_set_armor_proficiencies_for_class_delegates_without_commit(self):
        class_row = make_class_row()
        service, db = make_service()

        result = await service.set_armor_proficiencies_for_class(
            class_row, [ArmorProficiency.SHIELD.value], commit=False
        )

        assert result is class_row
        assert service.repository.armor_calls == [(class_row, [ArmorProficiency.SHIELD.value], False)]
        assert db.commits == 0
