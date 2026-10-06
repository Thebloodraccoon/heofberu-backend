"""Unit tests for SubclassRepository: class-scoped uniqueness (create and PATCH) and the brief listing."""

from types import SimpleNamespace

import pytest

from app.core.base.transaction import atomic
from app.core.exceptions import RecordAlreadyExistsError
from app.features.subclasses.crud.repository import SubclassRepository
from tests.unit.fakes import FakeAsyncSession


class RecordingSession(FakeAsyncSession):
    """Session that keeps the compiled text of every ``scalar`` statement."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scalar_sql: list[str] = []

    async def scalar(self, stmt):
        self.scalar_sql.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return await super().scalar(stmt)


@pytest.mark.unit
@pytest.mark.asyncio
class TestScopedUniqueness:
    async def test_create_allows_same_name_under_different_class(self):
        session = RecordingSession(scalar_results=[None])

        await SubclassRepository(session)._check_uniqueness({"name": "Champion", "class_id": 2})

        assert "subclasses.class_id = 2" in session.scalar_sql[0]

    async def test_create_rejects_same_name_under_same_class(self):
        repository = SubclassRepository(RecordingSession(scalar_results=[1]))

        with pytest.raises(RecordAlreadyExistsError):
            await repository._check_uniqueness({"name": "Champion", "class_id": 1})

    async def test_check_excludes_the_row_itself(self):
        session = RecordingSession(scalar_results=[None])

        await SubclassRepository(session)._check_uniqueness({"name": "Champion", "class_id": 1}, exclude_id=9)

        assert "subclasses.id != 9" in session.scalar_sql[0]

    async def test_check_without_name_skips_the_query(self):
        session = RecordingSession()

        await SubclassRepository(session)._check_uniqueness({"description": "only"})

        assert session.scalar_sql == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateScopesUniquenessByTheExistingRow:
    async def test_rename_is_checked_inside_the_subclass_own_class_only(self):
        """PATCH carries no class_id: the scope comes from the row, so a same-named subclass of ANOTHER class is no conflict."""

        session = RecordingSession(scalar_results=[None])
        row = SimpleNamespace(id=5, class_id=7, name="Old")

        async with atomic(session):
            await SubclassRepository(session).update(row, {"name": "Champion"})

        assert "subclasses.class_id = 7" in session.scalar_sql[0]
        assert "subclasses.id != 5" in session.scalar_sql[0]
        assert row.name == "Champion"
        assert session.commits == 1

    async def test_rename_clashing_with_a_sibling_is_rejected_and_not_applied(self):
        session = RecordingSession(scalar_results=[3])
        row = SimpleNamespace(id=5, class_id=7, name="Old")

        with pytest.raises(RecordAlreadyExistsError):
            await SubclassRepository(session).update(row, {"name": "Taken"})

        assert row.name == "Old"
        assert session.commits == 0

    async def test_description_only_update_runs_no_uniqueness_query(self):
        session = RecordingSession()
        row = SimpleNamespace(id=5, class_id=7, description="")

        async with atomic(session):
            await SubclassRepository(session).update(row, {"description": "text"})

        assert session.scalar_sql == []
        assert row.description == "text"

    async def test_update_only_flushes_until_atomic_exits(self):
        session = RecordingSession()
        row = SimpleNamespace(id=5, class_id=7, description="")

        async with atomic(session):
            await SubclassRepository(session).update(row, {"description": "text"})
            assert (session.flushes, session.commits) == (1, 0)
