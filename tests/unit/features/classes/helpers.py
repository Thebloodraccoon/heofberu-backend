"""Shared stand-ins for the class/subclass unit tests."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.constants import DiceType
from app.core.exceptions import RecordInUseError
from tests.unit.fakes import FakeRepository


def make_class_row(**overrides) -> SimpleNamespace:
    """A ``Class``-shaped row; relationship lists default to empty."""

    base = {
        "id": 1,
        "name": "Fighter",
        "hit_dice": DiceType.D10,
        "skill_choice_count": 2,
        "spellcasting_ability": None,
        "description": "",
        "image_url": None,
        "saving_throws": [],
        "armor_proficiencies": [],
        "weapon_proficiencies": [],
        "available_skills": [],
        "starting_items": [],
        "starting_choice_groups": [],
        "spell_slot_progression": [],
        "features": [],
        "subclasses": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeClassRepository(FakeRepository):
    """Class repository stand-in recording the child-row writes and the commit flag of every write."""

    def __init__(self, db, existing_by_id=None, *, in_use: bool = False, character_ids: list[int] | None = None):
        from app.models.classes.class_model import Class

        super().__init__(db, existing_by_id=existing_by_id, model=Class)
        self.in_use = in_use
        self.character_ids = character_ids or []
        self.update_calls: list[tuple[Any, dict, bool]] = []
        self.proficiency_calls: list[tuple[int, Any, list, bool]] = []
        self.skill_calls: list[tuple[int, Any, bool]] = []
        self.slot_calls: list[tuple[int, int, dict, bool]] = []
        self.fail_on_proficiencies: Exception | None = None
        self.names: dict[int, str] = {}
        self.slot_rows: list[Any] = []
        self.progression_features: list[Any] = []

    async def get_row(self, class_id):
        return self._rows.get(class_id)

    async def get_name(self, class_id):
        row = self._rows.get(class_id)
        return row.name if row is not None else None

    async def get_character_ids(self, class_id):
        return list(self.character_ids)

    async def update(self, db_obj, update_data, *, refresh=False, commit=True):
        self.update_calls.append((db_obj, dict(update_data), commit))
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        await self.commit_or_flush(commit=commit)
        return db_obj

    async def delete(self, db_obj):
        if self.in_use:
            raise RecordInUseError(model_name="Class", model_id=db_obj.id)
        return await super().delete(db_obj)

    async def set_proficiencies(self, class_id, kind, values, *, commit=True):
        if self.fail_on_proficiencies is not None:
            raise self.fail_on_proficiencies
        self.proficiency_calls.append((class_id, kind, list(values), commit))
        await self.commit_or_flush(commit=commit)

    async def set_available_skills(self, class_id, skills, *, commit=True):
        self.skill_calls.append((class_id, skills, commit))

    async def set_spell_slots(self, class_id, class_level, slots, *, commit=True):
        self.slot_calls.append((class_id, class_level, slots, commit))
        await self.commit_or_flush(commit=commit)

    async def get_spell_slot_rows(self, class_id):
        return self.slot_rows

    async def get_progression_features(self, class_id):
        return self.progression_features


@pytest.fixture
def purged(monkeypatch) -> AsyncMock:
    """Every cache purge (service-level and after-commit); inspect ``.await_args_list``."""

    mock = AsyncMock()
    monkeypatch.setattr("app.core.base.service.invalidate", mock)
    monkeypatch.setattr("app.core.cache.invalidation.invalidate", mock)
    return mock


def purged_namespaces(mock: AsyncMock) -> list[str]:
    """The namespaces purged so far, in order."""

    return [call.args[0] for call in mock.await_args_list]
