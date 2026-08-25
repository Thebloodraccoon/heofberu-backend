"""Unit tests for ClassWeaponService (set_weapon_proficiencies)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import DiceType, WeaponProficiency
from app.core.exceptions import RecordNotFoundError
from app.features.classes.schemas import WeaponProficienciesUpdate
from app.features.classes.weapons.service import ClassWeaponService
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


class FakeClassRepository(FakeRepository):
    """Class repository stand-in with the weapon-proficiency write."""

    def __init__(self, db, existing_by_id=None):
        super().__init__(db, existing_by_id=existing_by_id, model=Class)
        self.weapon_calls = []

    async def set_weapon_proficiencies(self, character_class, weapon_categories, *, commit=True):
        self.weapon_calls.append((character_class, weapon_categories, commit))
        character_class.weapon_proficiencies = [
            SimpleNamespace(weapon_category=weapon_category) for weapon_category in weapon_categories
        ]
        if commit:
            await self.db.commit()
        return character_class


@pytest.fixture(autouse=True)
def no_redis_invalidate(monkeypatch):
    monkeypatch.setattr("app.core.base.service.invalidate", AsyncMock())
    monkeypatch.setattr("app.features.classes.weapons.service.invalidate_class_cache", AsyncMock())


def make_service(existing_by_id=None):
    db = FakeAsyncSession()
    service = ClassWeaponService(db)
    service.repository = FakeClassRepository(db, existing_by_id=existing_by_id)
    return service, db


@pytest.mark.unit
@pytest.mark.asyncio
class TestClassWeaponService:
    async def test_set_weapon_proficiencies_replaces_and_returns_class(self):
        class_row = make_class_row()
        service, db = make_service(existing_by_id={1: class_row})
        data = WeaponProficienciesUpdate(weapon_proficiencies=[WeaponProficiency.SIMPLE, WeaponProficiency.MARTIAL])

        result = await service.set_weapon_proficiencies(1, data)

        assert result.id == 1
        assert service.repository.weapon_calls[0][0] is class_row
        assert service.repository.weapon_calls[0][1] == [WeaponProficiency.SIMPLE, WeaponProficiency.MARTIAL]
        assert service.repository.weapon_calls[0][2] is True
        assert db.commits == 1

    async def test_set_weapon_proficiencies_raises_when_class_missing(self):
        service, _ = make_service(existing_by_id={})
        data = WeaponProficienciesUpdate(weapon_proficiencies=[WeaponProficiency.SIMPLE])

        with pytest.raises(RecordNotFoundError):
            await service.set_weapon_proficiencies(99, data)

    async def test_set_weapon_proficiencies_for_class_delegates_without_commit(self):
        class_row = make_class_row()
        service, db = make_service()

        result = await service.set_weapon_proficiencies_for_class(
            class_row, [WeaponProficiency.MARTIAL.value], commit=False
        )

        assert result is class_row
        assert service.repository.weapon_calls == [(class_row, [WeaponProficiency.MARTIAL.value], False)]
        assert db.commits == 0
