"""Unit tests for the shared pagination primitives."""

import base64
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base

from app.core.exceptions import AppError
from app.core.pagination import (
    MAX_CURSOR_LENGTH,
    Cursor,
    CursorPage,
    InvalidCursorError,
    Page,
    cursor_page,
    decode_cursor,
    encode_cursor,
    keyset_condition,
    paginate,
    use_cursor,
)

Base = declarative_base()


class Row(Base):
    __tablename__ = "rows"
    id = Column(Integer, primary_key=True)
    name = Column(String)


def token(payload) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


class TestPaginate:
    @pytest.mark.parametrize(
        ("page", "size", "expected"),
        [(1, 10, (0, 10)), (3, 10, (20, 10)), (0, 10, (0, 10)), (1, 0, (0, 1)), (1, 10**6, (0, 1000))],
    )
    def test_converts_page_size_to_skip_limit(self, page, size, expected):
        assert paginate(page, size) == expected

    def test_envelopes(self):
        assert Page[int](items=[1], total=1, page=1, size=10).model_dump()["total"] == 1
        assert CursorPage[int](items=[1], next_cursor=None, size=10).model_dump() == {
            "items": [1],
            "next_cursor": None,
            "size": 10,
        }


class TestCursorRoundTrip:
    def test_string_value(self):
        assert decode_cursor(encode_cursor("name", "Aid", 7), "name") == Cursor("Aid", 7)

    def test_datetime_value(self):
        moment = datetime(2024, 5, 1, 12, 30, 15, 123456, tzinfo=timezone.utc)

        assert decode_cursor(encode_cursor("newest", moment, 3), "newest", as_datetime=True) == Cursor(moment, 3)

    def test_token_is_url_safe_and_unpadded(self):
        encoded = encode_cursor("name", "ы" * 20, 1)

        assert "=" not in encoded and "+" not in encoded and "/" not in encoded
        assert decode_cursor(encoded, "name").value == "ы" * 20


class TestDecodeValidation:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "!!!",
            "x" * (MAX_CURSOR_LENGTH + 1),
            token([1, 2]),
            token({"s": "name"}),
            token({"s": "name", "v": 5, "i": 1}),
            token({"s": "name", "v": "a", "i": "1"}),
            token({"s": "name", "v": "a", "i": True}),
            token({"s": "name", "v": "a", "i": 0}),
            token({"s": "other", "v": "a", "i": 1}),
        ],
    )
    def test_rejects_malformed_or_foreign_cursors(self, bad):
        with pytest.raises(InvalidCursorError):
            decode_cursor(bad, "name")

    def test_rejects_bad_datetime(self):
        with pytest.raises(InvalidCursorError):
            decode_cursor(token({"s": "newest", "v": "yesterday", "i": 1}), "newest", as_datetime=True)

    def test_error_is_a_422_app_error(self):
        assert issubclass(InvalidCursorError, AppError)
        assert InvalidCursorError.status_code == 422


class TestKeyset:
    @staticmethod
    def sql(descending):
        condition = keyset_condition(Row.name, Row.id, Cursor("b", 5), descending=descending)
        return str(
            select(Row.id)
            .where(condition)
            .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )

    def test_ascending_takes_strictly_greater_position(self):
        sql = self.sql(False)

        assert "rows.name > 'b'" in sql and "rows.name = 'b' AND rows.id > 5" in sql

    def test_descending_takes_strictly_smaller_position(self):
        sql = self.sql(True)

        assert "rows.name < 'b'" in sql and "rows.name = 'b' AND rows.id < 5" in sql


class TestCursorPage:
    def test_last_page_has_no_cursor(self):
        rows = [("a", 1), ("b", 2)]

        assert cursor_page(rows, 2, "name", lambda r: r) == (rows, None)

    def test_extra_row_trims_page_and_points_at_last_returned_row(self):
        rows = [("a", 1), ("b", 2), ("c", 3)]

        page, next_cursor = cursor_page(rows, 2, "name", lambda r: r)

        assert page == rows[:2]
        assert decode_cursor(next_cursor, "name") == Cursor("b", 2)


class TestUseCursor:
    @pytest.mark.parametrize(
        ("pagination", "cursor", "expected"),
        [("page", None, False), ("cursor", None, True), ("page", "abc", True), ("cursor", "abc", True)],
    )
    def test_opt_in(self, pagination, cursor, expected):
        assert use_cursor(pagination, cursor) is expected
