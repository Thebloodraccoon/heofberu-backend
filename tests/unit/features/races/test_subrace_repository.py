"""Unit tests for SubraceRepository (list_for_race / set_ability_bonuses / scoped uniqueness)."""

import pytest

from app.constants import AbilityScore
from app.core.exceptions import RecordAlreadyExistsError
from app.features.subraces.crud.repository import SubraceRepository
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


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceScopedUniqueness:
    async def test_create_allows_same_name_under_different_race(self):
        session = FakeAsyncSession(scalar_results=[None])
        repository = SubraceRepository(session)

        await repository._check_uniqueness({"name": "High Elf", "race_id": 2})

        assert len(session.executes) == 1

    async def test_create_rejects_same_name_under_same_race(self):
        session = FakeAsyncSession(scalar_results=[1])
        repository = SubraceRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            await repository._check_uniqueness({"name": "High Elf", "race_id": 1})

    async def test_update_allows_same_name_when_excluding_self(self):
        session = FakeAsyncSession(scalar_results=[None])
        repository = SubraceRepository(session)

        await repository._check_uniqueness({"name": "High Elf", "race_id": 1}, exclude_id=1)

        assert len(session.executes) == 1

    async def test_create_rejects_when_name_exists_without_race_id(self):
        session = FakeAsyncSession(scalar_results=[1])
        repository = SubraceRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            await repository._check_uniqueness({"name": "High Elf"})
