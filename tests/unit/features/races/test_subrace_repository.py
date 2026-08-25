"""Unit tests for SubraceRepository (list_for_race / set_ability_bonuses)."""

import pytest

from app.constants import AbilityScore
from app.features.races.subraces.crud.repository import SubraceRepository
from app.models.subrace_association_models import SubraceAbilityBonus
from app.models.subrace_model import Subrace
from tests.unit.fakes import FakeAsyncSession, FakeResult


def make_subrace(**overrides) -> Subrace:
    base = {
        "id": 1,
        "race_id": 1,
        "name": "High Elf",
        "description": "",
        "ability_bonuses": [],
    }
    base.update(overrides)
    return Subrace(**base)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceRepository:
    async def test_list_for_race_filters_by_race(self):
        session = FakeAsyncSession(execute_results=[FakeResult([make_subrace(id=1), make_subrace(id=2)])])
        repository = SubraceRepository(session)

        result = await repository.list_for_race(1)

        assert [item.id for item in result] == [1, 2]
        assert len(session.executes) == 1

    async def test_set_ability_bonuses_replaces_child_rows_and_commits(self):
        session = FakeAsyncSession()
        repository = SubraceRepository(session)
        subrace = make_subrace(id=1)

        result = await repository.set_ability_bonuses(
            subrace, [{"ability": AbilityScore.DEX, "bonus": 2}, {"ability": AbilityScore.INT, "bonus": 1}]
        )

        assert result is subrace
        assert len(session.added) == 2
        assert all(isinstance(row, SubraceAbilityBonus) for row in session.added)
        assert session.added[0].subrace_id == 1
        assert session.added[0].ability == AbilityScore.DEX
        assert session.commits == 1

    async def test_set_ability_bonuses_with_commit_false_flushes(self):
        session = FakeAsyncSession()
        repository = SubraceRepository(session)
        subrace = make_subrace(id=1)

        await repository.set_ability_bonuses(subrace, [], commit=False)

        assert session.flushes == 1
        assert session.commits == 0
