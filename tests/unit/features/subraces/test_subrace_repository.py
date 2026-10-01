"""Unit tests for SubraceRepository (listing, bonuses, race-scoped name uniqueness)."""

import pytest

from app.constants import AbilityScore
from app.core.exceptions import RecordAlreadyExistsError
from app.features.subraces.crud.repository import SubraceRepository
from app.models.races.subrace_association_models import SubraceAbilityBonus
from app.models.races.subrace_model import Subrace
from tests.unit.fakes import FakeAsyncSession, FakeResult


def make_subrace(**overrides) -> Subrace:
    base = {"id": 1, "race_id": 1, "name": "High Elf", "description": "", "ability_bonuses": []}
    base.update(overrides)
    return Subrace(**base)


class RecordingSession(FakeAsyncSession):
    """Keeps the statements passed to ``scalar`` so the scoping can be asserted."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scalar_statements = []

    async def scalar(self, stmt):
        self.scalar_statements.append(stmt)
        return await super().scalar(stmt)


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceRepository:
    async def test_list_for_race_filters_by_race(self):
        session = FakeAsyncSession(execute_results=[FakeResult([make_subrace(id=1), make_subrace(id=2)])])

        result = await SubraceRepository(session).list_for_race(1)

        assert [item.id for item in result] == [1, 2]
        assert len(session.executes) == 1

    async def test_race_exists(self):
        assert await SubraceRepository(FakeAsyncSession(scalar_results=[1])).race_exists(1) is True
        assert await SubraceRepository(FakeAsyncSession(scalar_results=[None])).race_exists(2) is False

    async def test_set_ability_bonuses_replaces_child_rows_and_commits(self):
        session = FakeAsyncSession()

        await SubraceRepository(session).set_ability_bonuses(
            1, [{"ability": AbilityScore.DEX, "bonus": 2}, {"ability": AbilityScore.INT, "bonus": 1}]
        )

        assert len(session.added) == 2
        assert all(isinstance(row, SubraceAbilityBonus) for row in session.added)
        assert session.added[0].subrace_id == 1
        assert session.added[0].ability == AbilityScore.DEX
        assert session.commits == 1

    async def test_set_ability_bonuses_with_commit_false_flushes(self):
        session = FakeAsyncSession()

        await SubraceRepository(session).set_ability_bonuses(1, [], commit=False)

        assert session.flushes == 1
        assert session.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubraceScopedUniqueness:
    async def test_create_allows_same_name_under_different_race(self):
        session = RecordingSession(scalar_results=[None])

        await SubraceRepository(session)._check_uniqueness({"name": "High Elf", "race_id": 2})

        assert "subraces.race_id = :race_id_1" in str(session.scalar_statements[0])

    async def test_create_rejects_same_name_under_same_race(self):
        session = FakeAsyncSession(scalar_results=[1])

        with pytest.raises(RecordAlreadyExistsError):
            await SubraceRepository(session)._check_uniqueness({"name": "High Elf", "race_id": 1})

    async def test_update_allows_same_name_when_excluding_self(self):
        session = FakeAsyncSession(scalar_results=[None])

        await SubraceRepository(session)._check_uniqueness({"name": "High Elf", "race_id": 1}, exclude_id=1)

    async def test_rename_is_scoped_to_the_subraces_own_race(self):
        """A PATCH carries no ``race_id``: the check must still be limited to the renamed row's race."""

        session = RecordingSession(scalar_results=[None])

        await SubraceRepository(session)._check_uniqueness({"name": "Drow"}, exclude_id=7)

        sql = str(session.scalar_statements[0])
        assert "subraces.race_id =" in sql
        assert "SELECT subraces.race_id" in sql
        assert "subraces.id !=" in sql

    async def test_rename_to_a_sibling_name_is_rejected(self):
        session = FakeAsyncSession(scalar_results=[3])

        with pytest.raises(RecordAlreadyExistsError):
            await SubraceRepository(session)._check_uniqueness({"name": "Drow"}, exclude_id=7)

    async def test_update_without_a_name_skips_the_query(self):
        session = RecordingSession()

        await SubraceRepository(session)._check_uniqueness({"description": "x"}, exclude_id=7)
        await SubraceRepository(session)._check_uniqueness({"name": None}, exclude_id=7)

        assert session.scalar_statements == []
