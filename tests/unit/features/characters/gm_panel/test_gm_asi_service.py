"""Unit tests for GmPanelAsiService: free-form ±ASI adjustments with no class level."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import ValidationError
import pytest

from app.constants import AbilityScore, ASILevelChoice
from app.features.characters.feats.exceptions import AbilityScoreCapExceededException
from app.features.characters.gm_panel.asi.schemas import GmAsiChoiceAdd
from app.features.characters.gm_panel.asi.schemas import GmAsiIncreaseInput as GmAsiIncreaseItem
from app.features.characters.gm_panel.asi.service import GmPanelAsiService
from app.features.characters.gm_panel.exceptions import (
    GmAsiAdjustmentNotFoundException,
    LevelTiedAsiChoiceException,
)
from app.models.character.character_model import Character
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
    """Stands in for CharacterStatsService: ``refresh`` returns the totals as they stand after the write."""

    def __init__(self, totals=None):
        self.totals = totals or dict(TOTALS)
        self.refresh_calls = []

    async def refresh(self, character, *, commit=True):
        self.refresh_calls.append((character, commit))
        return SimpleNamespace(**self.totals)


class FakeASIChoiceRepository:
    """Records choice-row writes and serves configured rows."""

    def __init__(self, choices_by_id=None, adjustments=None):
        self._by_id = choices_by_id or {}
        self._adjustments = adjustments or []
        self.add_calls = []
        self.delete_calls = []

    async def get_adjustments(self, character_id):
        return self._adjustments

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

    async def delete_adjustment(self, choice):
        self.delete_calls.append(choice)


@pytest.fixture(autouse=True)
def stub_cache_and_lock(monkeypatch):
    monkeypatch.setattr("app.features.characters.gm_panel.asi.service.invalidate_character_cache", AsyncMock())
    lock = AsyncMock()
    monkeypatch.setattr("app.features.characters.gm_panel.asi.service.lock_character", lock)
    return lock


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
        assert service.stats_service.refresh_calls == [(character, False)]

    async def test_raises_when_total_would_exceed_thirty(self):
        stats = FakeStatsService(totals={**TOTALS, "dexterity_total": 31})
        service = make_service(make_character(), stats=stats)

        with pytest.raises(AbilityScoreCapExceededException) as exc_info:
            await service.add_asi_adjustment(
                1,
                GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.DEX, amount=2)]),
                SimpleNamespace(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.current_total == 29
        assert exc_info.value.requested == 31
        assert service.repository.db.rollbacks == 1
        assert service.repository.db.commits == 0

    async def test_allows_adjustments_up_to_thirty(self):
        stats = FakeStatsService(totals={**TOTALS, "dexterity_total": 30})
        service = make_service(make_character(), stats=stats)

        await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.DEX, amount=2)]),
            SimpleNamespace(),
        )

        assert service.asi_repository.add_calls[0][3] == [{"ability": "DEX", "amount": 2}]  # 30 <= 30

    async def test_allows_negative_amounts(self):
        service = make_service(make_character())

        await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=-4)]),
            SimpleNamespace(),
        )

        assert service.asi_repository.add_calls[0][3] == [{"ability": "STR", "amount": -4}]

    async def test_every_increase_is_checked_against_the_thirty_cap(self):
        stats = FakeStatsService(totals={**TOTALS, "dexterity_total": 31})
        service = make_service(make_character(), stats=stats)

        with pytest.raises(AbilityScoreCapExceededException):
            await service.add_asi_adjustment(
                1,
                GmAsiChoiceAdd(
                    increases=[
                        GmAsiIncreaseItem(ability=AbilityScore.STR, amount=-2),
                        GmAsiIncreaseItem(ability=AbilityScore.DEX, amount=3),
                    ]
                ),
                SimpleNamespace(),
            )

        assert service.repository.db.rollbacks == 1

    async def test_writes_and_recomputes_once_inside_one_locked_transaction(self, stub_cache_and_lock):
        character = make_character()
        service = make_service(character)

        await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=1)]),
            SimpleNamespace(),
        )

        stub_cache_and_lock.assert_awaited_once()
        assert service.stats_service.refresh_calls == [(character, False)]
        assert service.repository.db.commits == 1
        assert service.repository.db.rollbacks == 0

    async def test_cache_is_invalidated_only_after_commit(self, monkeypatch):
        events = []
        service = make_service(make_character())

        async def commit():
            events.append("commit")

        async def invalidate(character_id):
            events.append("invalidate")

        service.repository.db.commit = commit
        monkeypatch.setattr("app.features.characters.gm_panel.asi.service.invalidate_character_cache", invalidate)

        await service.add_asi_adjustment(
            1,
            GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=1)]),
            SimpleNamespace(),
        )

        assert events == ["commit", "invalidate"]

    async def test_cache_is_not_invalidated_when_the_cap_check_rolls_back(self, monkeypatch):
        invalidate = AsyncMock()
        monkeypatch.setattr("app.features.characters.gm_panel.asi.service.invalidate_character_cache", invalidate)
        service = make_service(make_character(), stats=FakeStatsService(totals={**TOTALS, "strength_total": 31}))

        with pytest.raises(AbilityScoreCapExceededException):
            await service.add_asi_adjustment(
                1,
                GmAsiChoiceAdd(increases=[GmAsiIncreaseItem(ability=AbilityScore.STR, amount=1)]),
                SimpleNamespace(),
            )

        invalidate.assert_not_awaited()


@pytest.mark.unit
class TestGmAsiChoiceAddBounds:
    def test_empty_increases_are_rejected(self):
        with pytest.raises(ValidationError):
            GmAsiChoiceAdd(increases=[])

    def test_zero_amount_is_rejected(self):
        with pytest.raises(ValidationError):
            GmAsiChoiceAdd(increases=[{"ability": "STR", "amount": 0}])

    @pytest.mark.parametrize("amount", [31, -31, 2_000_000_000])
    def test_amount_beyond_the_ability_cap_is_rejected(self, amount):
        with pytest.raises(ValidationError):
            GmAsiChoiceAdd(increases=[{"ability": "STR", "amount": amount}])

    @pytest.mark.parametrize("amount", [30, -30, 1])
    def test_amount_within_bounds_is_accepted(self, amount):
        assert GmAsiChoiceAdd(increases=[{"ability": "STR", "amount": amount}]).increases[0].amount == amount

    def test_duplicate_ability_is_rejected(self):
        with pytest.raises(ValidationError):
            GmAsiChoiceAdd(increases=[{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 2}])


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetAsiAdjustments:
    async def test_lists_only_the_adjustments_the_repository_returns(self):
        gm_row = SimpleNamespace(id=3, character_id=1, class_level=None, increases=[])
        repository = FakeASIChoiceRepository(adjustments=[gm_row])
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

        await service.remove_asi_adjustment(1, 3, SimpleNamespace())

        assert repository.delete_calls == [row]
        assert service.stats_service.refresh_calls == [(character, False)]

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

        assert repository.delete_calls == []
        assert service.stats_service.refresh_calls == []
