"""Unit tests for BaseRepository._apply_search wildcard escaping."""

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.base.repository import BaseRepository


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "test_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


@pytest.fixture()
def sync_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class ItemRepository(BaseRepository[Item]):
    def __init__(self, db):
        super().__init__(Item, db, search_fields=["name"])


@pytest.mark.unit
class TestApplySearchWildcardEscaping:
    def _search(self, session, term):
        repo = ItemRepository(session)
        stmt = select(Item)
        stmt = repo._apply_search(stmt, term)
        return session.execute(stmt).scalars().all()

    def test_percent_literal_match(self, sync_session):
        sync_session.add_all(
            [
                Item(name="100% Completion"),
                Item(name="Complete"),
                Item(name="Partially"),
            ]
        )
        sync_session.commit()

        results = self._search(sync_session, "100%")
        assert len(results) == 1
        assert results[0].name == "100% Completion"

    def test_underscore_literal_match(self, sync_session):
        sync_session.add_all(
            [
                Item(name="test_item"),
                Item(name="test-item"),
                Item(name="testitem"),
            ]
        )
        sync_session.commit()

        results = self._search(sync_session, "test_item")
        assert len(results) == 1
        assert results[0].name == "test_item"

    def test_combined_wildcards(self, sync_session):
        sync_session.add_all(
            [
                Item(name="100%_done"),
                Item(name="100Xdone"),
                Item(name="100% done"),
            ]
        )
        sync_session.commit()

        results = self._search(sync_session, "100%_done")
        assert len(results) == 1
        assert results[0].name == "100%_done"

    def test_backslash_escape(self, sync_session):
        sync_session.add_all(
            [
                Item(name="path\\to\\file"),
                Item(name="path to file"),
            ]
        )
        sync_session.commit()

        results = self._search(sync_session, "path\\to")
        assert len(results) == 1
        assert results[0].name == "path\\to\\file"

    def test_normal_search_still_works(self, sync_session):
        sync_session.add_all(
            [
                Item(name="Longsword"),
                Item(name="Longbow"),
                Item(name="Dagger"),
            ]
        )
        sync_session.commit()

        results = self._search(sync_session, "Long")
        assert len(results) == 2

    def test_empty_search_returns_all(self, sync_session):
        sync_session.add_all([Item(name="A"), Item(name="B")])
        sync_session.commit()

        results = self._search(sync_session, "")
        assert len(results) == 2

    def test_none_search_returns_all(self, sync_session):
        sync_session.add_all([Item(name="A"), Item(name="B")])
        sync_session.commit()

        results = self._search(sync_session, None)
        assert len(results) == 2
