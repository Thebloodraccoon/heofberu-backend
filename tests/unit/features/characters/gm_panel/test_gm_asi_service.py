"""Unit tests for GmPanelAsiService: free-form ±ASI adjustments with no class level."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.constants import AbilityScore, ASILevelChoice
from app.features.characters.gm_panel.asi.schemas import GmAsiChoiceAdd, GmAsiIncreaseItem
from app.features.characters.gm_panel.asi.service import GmPanelAsiService
from app.features.characters.gm_panel.exceptions import (
    GmAsiAdjustmentNotFoundException,
    LevelTiedAsiChoiceException,
)
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException
from app.models.character_model import Character
from tests.unit.fakes import FakeAsyncSession


def make_character(**overrides) -> Character:
    base = {
        "id": 1,
        "owner_id": 1,
        "name": "Grog",
        "class_id": 1,
        "race_id": 5,
        "level": 5,
        "strength": 14,
        "dexterity": 10,
        "constitution": 12,
        "intelligence": 8,
        "wisdom": 9,
        "charisma": 11,
    }
    base.update(overrides)
    return Character(**base)


TOTALS = {
    "strength_total": 18,
    "dexterity_total": 10,
    "constitution_total": 12,
    "intelligence_total": 8,
    "wisdom_total": 9,
    "charisma_total": 11,
}


class FakeStatsService:
    """Stands in for CharacterStatsService with precomputed totals/caps."""

    def __init__(self, totals=None, caps=None):
        self.totals = totals or dict(TOTALS)
        self.caps = caps if caps is not None else dict.fromkeys(AbilityScore, 20)
        self.refresh_calls = []

    async def refresh(self, character):
        self.refresh_calls.append(character)

    async def compute(self, character):
        return self.totals

    async def resolve_ability_caps(self, character):
        return self.caps


class FakeASIChoiceRepository:
    """Records choice-row writes and serves configured rows."""

    def __init__(self, choices_by_id=None, all_choices=None):
        self._by_id = choices_by_id or {}
        self._all = all_choices or []
        self.add_calls = []
        self.remove_calls = []

    async def get_character_choices(self, character_id):
        return self._all

    async def add(self, character_id, class_level, choice_type, *, increases=None, commit=True):
        row = SimpleNamespace(
            id=3,
            character_id=character_id,
            class_level=class_level,
            increases=[SimpleNamespace(ability=i["ability"], amount=i["amount"]) for i in increases or []],
        )
        self.add_calls.append((character_id, class_level, choice_type, increases, commit))
        return row

    async def get_choice_by_id(self, character_id, choice_id):
        return self._by_id.get(choice_id)

    async def remove_choice(self, choice):
        self.remove_calls.append(choice)
        return True


@pytest.fixture(autouse=True)
def no_cache_invalidate(monkeypatch):
    monkeypatch.setattr("app.features.characters.gm_panel.asi.service.invalidate_character_cache", AsyncMock())


def make_service(character, *, stats=None, asi_repository=None):
    db = FakeAsyncSession()
    service = GmPanelAsiService(db)
    service.get_character_for_user = AsyncMock(return_value=character)
    service.stats_service = stats or FakeStatsService()
    service.asi_repository = asi_repository or FakeASIChoiceRepository()
    return service


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddAsiAdjustment:
    async def test_records_level_free_choice_row_with_typed_increases(self):
        character = make_character()
        service = make_service(character)

        result = await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=2)]),
            SimpleNamespace(),
        )

        assert result.id == 3
        assert result.character_id == 1
        assert service.asi_repository.add_calls == [
            (1, None, ASILevelChoice.ASI, [{"ability": "STR", "amount": 2}], False)
        ]
        assert service.stats_service.refresh_calls == [character]

    async def test_enforces_effective_total_cap(self):
        stats = FakeStatsService(totals={**TOTALS, "dexterity_total": 19})
        service = make_service(make_character(), stats=stats)

        with pytest.raises(AbilityScoreCapExceededException) as exc_info:
            await service.add_asi_adjustment(
                1,
                GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.DEX, amount=2)]),
                SimpleNamespace(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.current_total == 19
        assert exc_info.value.requested == 21
        assert service.asi_repository.add_calls == []
        assert service.stats_service.refresh_calls == []

    async def test_allows_negative_amounts(self):
        service = make_service(make_character())

        await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=-4)]),
            SimpleNamespace(),
        )

        assert service.asi_repository.add_calls[0][3] == [{"ability": "STR", "amount": -4}]

    async def test_every_increase_is_checked_against_its_own_cap(self):
        stats = FakeStatsService(
            totals=TOTALS,
            caps={**dict.fromkeys(AbilityScore, 20), AbilityScore.INT: 10},
        )
        service = make_service(make_character(), stats=stats)

        with pytest.raises(AbilityScoreCapExceededException):
            await service.add_asi_adjustment(
                1,
                GmAsiChoiceAdd(
                    increases=[
                        GmAsiIncreaseItem(ability=AbilityScore.STR, amount=-2),
                        GmAsiIncreaseItem(ability=AbilityScore.INT, amount=3),
                    ]
                ),
                SimpleNamespace(),
            )

        assert service.asi_repository.add_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetAsiAdjustments:
    async def test_filters_out_level_tied_choices(self):
        gm_row = SimpleNamespace(id=3, character_id=1, class_level=None, increases=[])
        level_tied = SimpleNamespace(id=4, character_id=1, class_level=4, increases=[])
        repository = FakeASIChoiceRepository(all_choices=[gm_row, level_tied])
        character = make_character()
        service = make_service(character, asi_repository=repository)

        result = await service.get_asi_adjustments(1, SimpleNamespace())

        assert [row.id for row in result] == [3]
        service.get_character_for_user.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveAsiAdjustment:
    async def test_deletes_free_row_and_refreshes_cache(self):
        character = make_character()
        row = SimpleNamespace(id=3, character_id=1, class_level=None, increases=[])
        repository = FakeASIChoiceRepository(choices_by_id={3: row})
        service = make_service(character, asi_repository=repository)

        result = await service.remove_asi_adjustment(1, 3, SimpleNamespace())

        assert result is True
        assert repository.remove_calls == [row]
        assert service.stats_service.refresh_calls == [character]

    async def test_unknown_adjustment_raises(self):
        service = make_service(make_character())

        with pytest.raises(GmAsiAdjustmentNotFoundException) as exc_info:
            await service.remove_asi_adjustment(1, 99, SimpleNamespace())

        assert exc_info.value.status_code == 404

    async def test_refuses_level_tied_choice(self):
        row = SimpleNamespace(id=4, character_id=1, class_level=8, increases=[])
        repository = FakeASIChoiceRepository(choices_by_id={4: row})
        service = make_service(make_character(), asi_repository=repository)

        with pytest.raises(LevelTiedAsiChoiceException):
            await service.remove_asi_adjustment(1, 4, SimpleNamespace())

        assert repository.remove_calls == []
        assert service.stats_service.refresh_calls == []
