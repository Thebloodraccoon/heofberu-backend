"""
Pagination primitives shared by every listing.

Public convention: ``page`` (1-indexed) / ``size`` query parameters and the
:class:`Page` ``{items, total, page, size}`` envelope. ``skip``/``limit`` are
internal (repositories) and produced from ``page``/``size`` by :func:`paginate`.

Large listings (articles, characters, spells) also offer an opt-in keyset
alternative: the client sends ``pagination=cursor`` (then ``cursor=<next_cursor>``)
and receives a :class:`CursorPage` ``{items, next_cursor, size}``. Rows are ordered
by ``(sort key, id)`` and the cursor is an opaque url-safe base64 token holding the
last row's sort value and id; a malformed or foreign cursor is a 422
(:class:`InvalidCursorError`). No ``total`` is computed in cursor mode.
"""

import base64
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Annotated, Any, Generic, Literal

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import and_, or_
from starlette import status
from typing_extensions import TypeVar

from app.core.exceptions import AppError

ItemSchema = TypeVar("ItemSchema", bound=BaseModel)

MAX_PAGE_SIZE = 1000
MAX_CURSOR_LENGTH = 512

PaginationQuery = Annotated[
    Literal["page", "cursor"],
    Query(description="`page` (default): `page`/`size` with `total`. `cursor`: keyset pagination, see `cursor`."),
]
CursorQuery = Annotated[
    str | None,
    Query(
        max_length=MAX_CURSOR_LENGTH,
        description="Opaque `next_cursor` of the previous response (implies `pagination=cursor`; omit for the first "
        "page). Valid only with the same `sort`; an invalid cursor is a 422.",
    ),
]


def use_cursor(pagination: str, cursor: str | None) -> bool:
    """True when the caller opted into keyset pagination (``pagination=cursor`` or a ``cursor`` token)."""

    return pagination == "cursor" or cursor is not None


class Page(BaseModel, Generic[ItemSchema]):
    """Generic ``{items, total, page, size}`` envelope for an offset-paginated listing."""

    items: list[ItemSchema]
    total: int
    page: int
    size: int


class CursorPage(BaseModel, Generic[ItemSchema]):
    """``{items, next_cursor, size}`` envelope for a keyset-paginated listing (``next_cursor`` is null on the last page)."""

    items: list[ItemSchema]
    next_cursor: str | None
    size: int


def paginate(page: int, size: int) -> tuple[int, int]:
    """
    Convert a 1-indexed ``(page, size)`` into the repository's 0-indexed ``(skip, limit)``.

    Defensive clamp: ``page >= 1`` and ``1 <= size <= MAX_PAGE_SIZE`` even if a
    router forgot to bound the query parameters.
    """

    page = max(page, 1)
    size = min(max(size, 1), MAX_PAGE_SIZE)
    return (page - 1) * size, size


class InvalidCursorError(AppError):
    """Raised (422) when a ``cursor`` is malformed, too long, or was issued for another sort."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, reason: str = "Invalid cursor"):
        super().__init__(reason)


@dataclass(frozen=True)
class Cursor:
    """Decoded position: the last returned row's sort value and id."""

    value: str | datetime
    id: int


def encode_cursor(sort: str, value: str | datetime, row_id: int) -> str:
    """Build the opaque cursor for the row ``(value, row_id)`` of the ordering named ``sort``."""

    payload = {"s": sort, "v": value.isoformat() if isinstance(value, datetime) else value, "i": row_id}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(token: str, sort: str, *, as_datetime: bool = False) -> Cursor:
    """
    Validate and decode ``token`` for the ordering named ``sort``.

    ``as_datetime`` parses the sort value back into a ``datetime`` (timestamp orderings).

    Raises:
        InvalidCursorError: Too long, not base64/JSON, wrong shape, or issued for a different ``sort``.
    """

    if not token or len(token) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError()

    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        value, row_id = payload["v"], payload["i"]
        valid = (
            payload["s"] == sort
            and isinstance(value, str)
            and isinstance(row_id, int)
            and not isinstance(row_id, bool)
            and row_id > 0
        )
        if valid and as_datetime:
            value = datetime.fromisoformat(value)
    except (ValueError, KeyError, TypeError):
        raise InvalidCursorError() from None

    if not valid:
        raise InvalidCursorError()

    return Cursor(value=value, id=row_id)


def keyset_condition(sort_column: Any, id_column: Any, cursor: Cursor, *, descending: bool = False) -> Any:
    """WHERE clause selecting the rows strictly after ``cursor`` when ordered by ``(sort_column, id_column)`` in one direction."""

    if descending:
        return or_(sort_column < cursor.value, and_(sort_column == cursor.value, id_column < cursor.id))

    return or_(sort_column > cursor.value, and_(sort_column == cursor.value, id_column > cursor.id))


def cursor_page(rows: list[Any], size: int, sort: str, key: Any) -> tuple[list[Any], str | None]:
    """
    Split rows fetched with ``LIMIT size + 1`` into the page and its ``next_cursor``.

    ``key(row)`` returns the row's ``(sort value, id)``.
    """

    if len(rows) <= size:
        return rows, None

    page_rows = rows[:size]
    value, row_id = key(page_rows[-1])
    return page_rows, encode_cursor(sort, value, row_id)
