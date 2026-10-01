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


class Widget(Base):
    __tablename__ = "test_widgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    image_url: Mapped[str] = mapped_column(String(200), default="")
    hashed_password: Mapped[str] = mapped_column(String(200), default="")


def _sql(stmt) -> str:
    return " ".join(str(stmt).split())


@pytest.mark.unit
class TestDefaultSearchFields:
    def test_secrets_and_urls_are_never_auto_searched(self, sync_session):
        repo = BaseRepository(Widget, sync_session)

        assert repo._search_fields == ["name"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeterministicOrdering:
    async def test_get_brief_defaults_to_id_order(self):
        from tests.unit.fakes import FakeAsyncSession, FakeResult

        db = FakeAsyncSession(execute_results=[FakeResult([])])

        await BaseRepository(Widget, db).get_brief(Widget.id, Widget.name)

        assert "ORDER BY test_widgets.id" in _sql(db.executes[0])

    async def test_get_brief_adds_id_as_tie_break(self):
        from tests.unit.fakes import FakeAsyncSession, FakeResult

        db = FakeAsyncSession(execute_results=[FakeResult([])])

        await BaseRepository(Widget, db).get_brief(Widget.id, Widget.name, order_by=Widget.name)

        assert "ORDER BY test_widgets.name, test_widgets.id" in _sql(db.executes[0])

    async def test_get_all_adds_id_as_tie_break(self):
        from tests.unit.fakes import FakeAsyncSession, FakeResult

        db = FakeAsyncSession(execute_results=[FakeResult([])])

        await BaseRepository(Widget, db).get_all(order_by=Widget.name)

        assert "ORDER BY test_widgets.name, test_widgets.id" in _sql(db.executes[0])

    async def test_explicit_id_order_is_not_duplicated(self):
        from tests.unit.fakes import FakeAsyncSession, FakeResult

        db = FakeAsyncSession(execute_results=[FakeResult([])])

        await BaseRepository(Widget, db).get_all(order_by=Widget.id.desc())

        assert "ORDER BY test_widgets.id DESC" in _sql(db.executes[0])
        assert "test_widgets.id DESC, test_widgets.id" not in _sql(db.executes[0])

    async def test_multiple_order_columns_keep_their_order(self):
        repo = BaseRepository(Widget, None)

        clauses = repo._ordering([Widget.name, Widget.image_url])

        assert clauses == [Widget.name, Widget.image_url, Widget.id]
