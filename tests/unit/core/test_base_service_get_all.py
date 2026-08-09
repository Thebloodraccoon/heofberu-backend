"""Unit tests for ``BaseService.get_all`` routing.

Covers the three listing paths: column-select through
``repository.get_brief`` when ``get_all_schema`` has no relationship
fields, eager ``repository.get_all`` fallback when it does, and the plain
full-record path when ``get_all_schema`` is ``None``. The repository is a
recording fake; SQLAlchemy models are declared inline so
``inspect(model).relationships`` works without a database.
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

from app.core.base_service import BaseService

_TestBase = declarative_base()


class ItemModel(_TestBase):
    __tablename__ = "test_items"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class BookModel(_TestBase):
    __tablename__ = "test_books"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    author_id = Column(ForeignKey("test_authors.id"))


class AuthorModel(_TestBase):
    __tablename__ = "test_authors"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    books = relationship("BookModel")


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    books: list[BookOut] = []


class FakeRepository:
    """Recording fake standing in for ``BaseRepository``."""

    def __init__(self, model, rows):
        self.model = model
        self.rows = rows
        self.get_brief_calls = []
        self.get_all_calls = []
        self.count_calls = []

    def get_brief(self, *columns, order_by=None, skip=0, limit=100, filters=None, search=None):
        self.get_brief_calls.append((columns, order_by, skip, limit, filters, search))
        return self.rows[skip : skip + limit]

    def get_all(self, *, skip=0, limit=100, filters=None, search=None, order_by=None):
        self.get_all_calls.append((skip, limit, filters, search, order_by))
        return self.rows[skip : skip + limit]

    def count(self, *, filters=None, search=None):
        self.count_calls.append((filters, search))
        return len(self.rows)


def make_service(model, repo, response_schema, get_all_schema):
    return BaseService(
        repository=repo,
        response_schema=response_schema,
        get_all_schema=get_all_schema,
    )


@pytest.mark.unit
class TestGetAllColumnSelect:
    def test_schema_without_relationships_uses_get_brief(self):
        rows = [
            SimpleNamespace(id=1, name="Sword"),
            SimpleNamespace(id=2, name="Shield"),
        ]
        repo = FakeRepository(ItemModel, rows)
        service = make_service(ItemModel, repo, ItemOut, ItemOut)

        page = service.get_all(page=1, size=10)

        assert page.total == 2
        assert page.page == 1
        assert page.size == 10
        assert [item.id for item in page.items] == [1, 2]
        assert [item.name for item in page.items] == ["Sword", "Shield"]
        assert repo.get_brief_calls[0][0] == (ItemModel.id, ItemModel.name)
        assert repo.get_brief_calls[0][1] is ItemModel.id
        assert repo.get_all_calls == []

    def test_get_brief_respects_pagination(self):
        rows = [SimpleNamespace(id=1, name="A"), SimpleNamespace(id=2, name="B"),
                SimpleNamespace(id=3, name="C"), SimpleNamespace(id=4, name="D")]
        repo = FakeRepository(ItemModel, rows)
        service = make_service(ItemModel, repo, ItemOut, ItemOut)

        page = service.get_all(page=2, size=2)

        assert [item.id for item in page.items] == [3, 4]
        assert repo.get_brief_calls[0][2] == 2  # skip
        assert repo.get_brief_calls[0][3] == 2  # limit
        assert repo.count_calls == [(None, None)]

    def test_filters_and_search_forwarded_to_repository(self):
        rows = [SimpleNamespace(id=1, name="Sword")]
        repo = FakeRepository(ItemModel, rows)
        service = make_service(ItemModel, repo, ItemOut, ItemOut)

        service.get_all(filters={"name": "Sword"}, search="wor")

        assert repo.get_brief_calls[0][4] == {"name": "Sword"}
        assert repo.get_brief_calls[0][5] == "wor"
        assert repo.count_calls == [({"name": "Sword"}, "wor")]


@pytest.mark.unit
class TestGetAllRelationshipFallback:
    def test_schema_with_relationship_field_uses_get_all(self):
        repo = FakeRepository(
            AuthorModel,
            [SimpleNamespace(id=1, name="Tolkien", books=[])],
        )
        service = make_service(AuthorModel, repo, AuthorOut, AuthorOut)

        page = service.get_all(page=1, size=10)

        assert repo.get_brief_calls == []
        assert repo.get_all_calls == [(0, 10, None, None, None)]
        assert page.items[0].name == "Tolkien"
        assert page.items[0].books == []


@pytest.mark.unit
class TestGetAllFullRecords:
    def test_none_schema_serializes_full_records(self):
        rows = [SimpleNamespace(id=1, name="Sword")]
        repo = FakeRepository(ItemModel, rows)
        service = make_service(ItemModel, repo, ItemOut, None)

        page = service.get_all(page=1, size=10)

        assert repo.get_brief_calls == []
        assert repo.get_all_calls == [(0, 10, None, None, None)]
        assert page.items[0].name == "Sword"
        assert page.total == 1
