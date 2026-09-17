"""Unit tests for CharacterStatsRepository (the ability-score cache repo)."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.repository import CharacterStatsRepository
from app.models.character.character_ability_score_model import CharacterAbilityScore
from tests.unit.fakes import FakeAsyncSession, FakeResult


def make_session(rows):
    return FakeAsyncSession(execute_results=[FakeResult(rows)])


def make_cache_row(character_id=1, **overrides):
    base = {
        "character_id": character_id,
        "strength_total": 14,
        "dexterity_total": 10,
        "constitution_total": 12,
        "intelligence_total": 8,
        "wisdom_total": 9,
        "charisma_total": 11,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.unit
@pytest.mark.asyncio
class TestCharacterStatsRepository:
    async def test_get_by_character_id_returns_row(self):
        row = make_cache_row()
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_by_character_id(1)

        assert result is row

    async def test_get_by_character_id_returns_none_when_missing(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_by_character_id(1)

        assert result is None

    async def test_get_many_by_character_ids_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_many_by_character_ids([])

        assert result == {}

    async def test_get_many_by_character_ids_groups_by_character_id(self):
        row1 = make_cache_row(character_id=1)
        row2 = make_cache_row(character_id=2)
        repository = CharacterStatsRepository(make_session([row1, row2]))

        result = await repository.get_many_by_character_ids([1, 2])

        assert result == {1: row1, 2: row2}

    async def test_get_race_bonuses_none_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_race_bonuses(None)

        assert result == []

    async def test_get_race_bonuses_returns_rows(self):
        row = SimpleNamespace(race_id=5, ability=AbilityScore.DEX, bonus=2)
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_race_bonuses(5)

        assert result == [row]

    async def test_get_subrace_bonuses_none_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_subrace_bonuses(None)

        assert result == []

    async def test_get_subrace_bonuses_returns_rows(self):
        row = SimpleNamespace(subrace_id=7, ability=AbilityScore.INT, bonus=1)
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_subrace_bonuses(7)

        assert result == [row]

    async def test_get_feature_increases_merges_fixed_and_option_rows(self):
        """get_feature_increases returns both fixed (feature-owned) and option (choice-pick) effect rows."""
        fixed_row = SimpleNamespace(id=10, ability=AbilityScore.STR, amount=2)
        option_row = SimpleNamespace(id=20, ability=AbilityScore.DEX, amount=1)
        # First execute returns fixed rows, second returns option rows
        session = FakeAsyncSession(execute_results=[FakeResult([fixed_row]), FakeResult([option_row])])
        repository = CharacterStatsRepository(session)

        result = await repository.get_feature_increases(1)

        assert len(result) == 2
        assert result[0] is fixed_row
        assert result[1] is option_row

    async def test_get_feature_increases_empty_when_no_grants(self):
        session = FakeAsyncSession(execute_results=[FakeResult([]), FakeResult([])])
        repository = CharacterStatsRepository(session)

        result = await repository.get_feature_increases(1)

        assert result == []

    async def test_get_asi_increases_returns_counted_rows(self):
        row = SimpleNamespace(id=1, character_asi_choice_id=9, ability=AbilityScore.STR, amount=2)
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_asi_increases(1)

        assert result == [row]

    async def test_upsert_creates_new_row_when_missing(self):
        session = FakeAsyncSession(execute_results=[FakeResult([])])
        repository = CharacterStatsRepository(session)
        totals = {"strength_total": 15, "dexterity_total": 12}

        cache = await repository.upsert(1, totals)

        assert isinstance(cache, CharacterAbilityScore)
        assert cache.character_id == 1
        assert cache.strength_total == 15
        assert session.commits == 1
        assert session.refreshed == [cache]
        assert session.added == [cache]

    async def test_upsert_updates_existing_row(self):
        existing = make_cache_row()
        session = FakeAsyncSession(execute_results=[FakeResult([existing])])
        repository = CharacterStatsRepository(session)

        cache = await repository.upsert(1, {"strength_total": 20, "charisma_total": 18})

        assert cache is existing
        assert cache.strength_total == 20
        assert cache.charisma_total == 18
        assert existing.dexterity_total == 10
        assert session.commits == 1
        assert session.added == []

    async def test_get_race_bonuses_many_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_race_bonuses_many([])

        assert result == {}

    async def test_get_race_bonuses_many_groups_by_race_id(self):
        row1 = SimpleNamespace(race_id=5, ability=AbilityScore.DEX, bonus=2)
        row2 = SimpleNamespace(race_id=6, ability=AbilityScore.STR, bonus=1)
        repository = CharacterStatsRepository(make_session([row1, row2]))

        result = await repository.get_race_bonuses_many([5, 6, None])

        assert result == {5: [row1], 6: [row2]}

    async def test_get_subrace_bonuses_many_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_subrace_bonuses_many([])

        assert result == {}

    async def test_get_subrace_bonuses_many_groups_by_subrace_id(self):
        row = SimpleNamespace(subrace_id=7, ability=AbilityScore.INT, bonus=1)
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_subrace_bonuses_many([7])

        assert result == {7: [row]}

    async def test_get_asi_increases_many_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_asi_increases_many([])

        assert result == {}

    async def test_get_asi_increases_many_groups_by_character_id(self):
        row1 = SimpleNamespace(id=1, ability=AbilityScore.STR, amount=2)
        row2 = SimpleNamespace(id=2, ability=AbilityScore.DEX, amount=1)
        session = FakeAsyncSession(execute_results=[FakeResult([(row1, 1), (row2, 2)])])
        repository = CharacterStatsRepository(session)

        result = await repository.get_asi_increases_many([1, 2])

        assert result == {1: [row1], 2: [row2]}

    async def test_get_feature_increases_many_empty_ids_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_feature_increases_many([])

        assert result == {}

    async def test_get_feature_increases_many_merges_fixed_and_option_rows_per_character(self):
        fixed_row = SimpleNamespace(id=10, ability=AbilityScore.STR, amount=2)
        option_row = SimpleNamespace(id=20, ability=AbilityScore.DEX, amount=1)
        session = FakeAsyncSession(
            execute_results=[FakeResult([(fixed_row, 1)]), FakeResult([(option_row, 2)])]
        )
        repository = CharacterStatsRepository(session)

        result = await repository.get_feature_increases_many([1, 2])

        assert result == {1: [fixed_row], 2: [option_row]}

    async def test_get_feature_increases_many_defaults_every_id_to_empty_list(self):
        session = FakeAsyncSession(execute_results=[FakeResult([]), FakeResult([])])
        repository = CharacterStatsRepository(session)

        result = await repository.get_feature_increases_many([1, 2])

        assert result == {1: [], 2: []}

    async def test_upsert_many_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.upsert_many({})

        assert result == {}

    async def test_upsert_many_creates_and_updates_in_one_batch(self):
        existing = make_cache_row(character_id=2)
        session = FakeAsyncSession(execute_results=[FakeResult([existing])])
        repository = CharacterStatsRepository(session)
        totals = {1: {"strength_total": 15}, 2: {"strength_total": 20}}

        result = await repository.upsert_many(totals, commit=False)

        assert set(result) == {1, 2}
        assert result[1].character_id == 1
        assert result[1].strength_total == 15
        assert result[2] is existing
        assert result[2].strength_total == 20
        assert session.commits == 0
        assert session.flushes == 1
        assert session.added == [result[1]]

    async def test_get_classes_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_classes([])

        assert result == {}

    async def test_get_classes_groups_by_id(self):
        row = SimpleNamespace(id=1, name="Fighter")
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_classes([1])

        assert result == {1: row}

    async def test_get_races_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_races([])

        assert result == {}

    async def test_get_races_groups_by_id(self):
        row = SimpleNamespace(id=5, name="Elf")
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_races([5])

        assert result == {5: row}
