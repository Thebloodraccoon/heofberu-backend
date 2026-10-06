"""Unit tests for CharacterStatsRepository (the ability-score cache repo)."""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.constants import AbilityScore, DiceType
from app.core.base.transaction import atomic
from app.features.characters.ability_score.repository import CharacterStatsRepository
from tests.unit.fakes import FakeAsyncSession, FakeResult


class UpsertSession(FakeAsyncSession):
    """FakeAsyncSession whose ``execute`` accepts execution options (ORM INSERT ... RETURNING)."""

    def __init__(self, rows):
        super().__init__(execute_results=[FakeResult(rows)])

    async def execute(self, stmt, params=None, execution_options=None):
        return await super().execute(stmt, params)


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
        session = FakeAsyncSession(execute_results=[FakeResult([(fixed_row, 1)]), FakeResult([(option_row, 2)])])
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

    async def test_upsert_is_a_single_insert_on_conflict_do_update(self):
        row = make_cache_row(strength_total=15)
        session = UpsertSession([row])
        repository = CharacterStatsRepository(session)

        async with atomic(session):
            cache = await repository.upsert(1, {"strength_total": 15, "dexterity_total": 12})

        assert cache is row
        assert len(session.executes) == 1
        sql = str(session.executes[0].compile(dialect=postgresql.dialect())).upper()
        assert "ON CONFLICT (CHARACTER_ID) DO UPDATE" in sql
        assert "UPDATED_AT" in sql
        assert session.commits == 1

    async def test_upsert_many_returns_rows_by_character_id_and_flushes_without_committing(self):
        rows = [make_cache_row(character_id=1), make_cache_row(character_id=2)]
        session = UpsertSession(rows)
        repository = CharacterStatsRepository(session)

        async with atomic(session):
            result = await repository.upsert_many({2: {"strength_total": 20}, 1: {"strength_total": 15}})
            assert session.flushes == 1

        assert result == {1: rows[0], 2: rows[1]}

    async def test_get_hit_dice_maps_class_ids_to_die_values(self):
        session = FakeAsyncSession(execute_results=[FakeResult([(1, DiceType.D10), (2, DiceType.D6)])])
        repository = CharacterStatsRepository(session)

        assert await repository.get_hit_dice([1, 2]) == {1: "D10", 2: "D6"}

    async def test_get_hit_dice_without_ids_skips_the_query(self):
        session = FakeAsyncSession()
        repository = CharacterStatsRepository(session)

        assert await repository.get_hit_dice([]) == {}
        assert session.executes == []

    async def test_get_names_map_ids_to_names(self):
        session = FakeAsyncSession(execute_results=[FakeResult([(5, "Elf")]), FakeResult([(7, "High Elf")])])
        repository = CharacterStatsRepository(session)

        assert await repository.get_race_names([5]) == {5: "Elf"}
        assert await repository.get_subrace_names([7]) == {7: "High Elf"}
        assert await repository.get_race_names([]) == {}
