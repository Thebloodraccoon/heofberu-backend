"""Unit tests for SubclassRepository (scoped uniqueness checks)."""

import pytest

from app.core.exceptions import RecordAlreadyExistsError
from app.features.subclasses.crud.repository import SubclassRepository
from tests.unit.fakes import FakeAsyncSession


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubclassScopedUniqueness:
    async def test_create_allows_same_name_under_different_class(self):
        session = FakeAsyncSession(scalar_results=[None])
        repository = SubclassRepository(session)

        await repository._check_uniqueness({"name": "Champion", "class_id": 2})

    async def test_create_rejects_same_name_under_same_class(self):
        session = FakeAsyncSession(scalar_results=[1])
        repository = SubclassRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            await repository._check_uniqueness({"name": "Champion", "class_id": 1})

    async def test_update_allows_same_name_when_excluding_self(self):
        session = FakeAsyncSession(scalar_results=[None])
        repository = SubclassRepository(session)

        await repository._check_uniqueness({"name": "Champion", "class_id": 1}, exclude_id=1)

    async def test_create_rejects_when_name_exists_without_class_id(self):
        session = FakeAsyncSession(scalar_results=[1])
        repository = SubclassRepository(session)

        with pytest.raises(RecordAlreadyExistsError):
            await repository._check_uniqueness({"name": "Champion"})
