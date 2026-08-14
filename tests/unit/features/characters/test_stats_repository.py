"""Unit tests for CharacterStatsRepository (the ability-score cache repo)."""

from types import SimpleNamespace

import pytest

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import ArmorSpec
from app.features.characters.ability_score.repository import CharacterStatsRepository
from app.models.character_ability_score_model import CharacterAbilityScore
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

    async def test_get_feat_increases_returns_rows(self):
        row = SimpleNamespace(id=1, feat_id=3, ability=AbilityScore.STR, amount=1)
        repository = CharacterStatsRepository(make_session([row]))

        result = await repository.get_feat_increases(1)

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

    async def test_get_armor_by_character_ids_empty_returns_empty(self):
        repository = CharacterStatsRepository(make_session([]))

        result = await repository.get_armor_by_character_ids([])

        assert result == {}

    async def test_get_armor_by_character_ids_groups_armor_specs(self):
        rows = [
            SimpleNamespace(
                character_id=1,
                item=SimpleNamespace(armor_class_base=16, armor_class_dex_bonus=True, armor_class_max_dex_bonus=2),
            ),
            SimpleNamespace(
                character_id=1,
                item=SimpleNamespace(armor_class_base=14, armor_class_dex_bonus=False, armor_class_max_dex_bonus=None),
            ),
        ]
        repository = CharacterStatsRepository(make_session(rows))

        result = await repository.get_armor_by_character_ids([1])

        assert result == {
            1: [
                ArmorSpec(base=16, dex_bonus=True, max_dex_bonus=2),
                ArmorSpec(base=14, dex_bonus=False, max_dex_bonus=None),
            ]
        }
