"""Article listing and search: pagination and the nesting of listing rows into response objects."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, paginate
from app.features.articles.listing.filters import ArticleFilters
from app.features.articles.listing.repository import ArticleListingRepository
from app.features.articles.listing.schemas import ArticleGetAllResponse, ArticleSearchResult


def _nest_row(row) -> dict:
    """Listing row (flat ``subtype_*``/``author_*`` columns) -> dict with nested ``subtype``/``author`` objects."""

    data = dict(row._mapping)
    subtype_id, name = data.pop("subtype_id"), data.pop("subtype_name")
    data["subtype"] = {"id": subtype_id, "name": name} if subtype_id is not None else None
    author_id, username = data.pop("author_id"), data.pop("author_username")
    data["author"] = {"id": author_id, "username": username} if author_id is not None else None
    return data


class ArticleListingService:
    """
    ``GET /articles`` and ``GET /articles/search``.

    Not cached: results depend on the reader's visibility and on every filter, and change with any article write.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the listing repository."""

        self.repository = ArticleListingRepository(db)

    async def list_articles(
        self,
        filters: ArticleFilters,
        *,
        page: int,
        size: int,
        sort: str,
        cursor: str | None = None,
        use_cursor: bool = False,
    ) -> Page[ArticleGetAllResponse] | CursorPage[ArticleGetAllResponse]:
        """
        Filtered, sorted listing.

        Offset ``Page`` by default; with ``use_cursor`` a keyset ``CursorPage`` ordered by ``(sort key, id)``
        whose ``cursor`` must have been issued for the same ``sort`` (422 otherwise).
        """

        skip, limit = paginate(page, size)
        after = decode_cursor(cursor, sort, as_datetime=sort != "title") if cursor is not None else None
        rows, total = await self.repository.list_articles(
            filters, skip=skip, limit=size + 1 if use_cursor else limit, sort=sort, after=after
        )
        if use_cursor:
            rows, next_cursor = cursor_page(rows, size, sort, lambda row: (row.sort_value, row.id))
            items = [ArticleGetAllResponse.model_validate(_nest_row(row)) for row in rows]
            return CursorPage(items=items, next_cursor=next_cursor, size=size)

        items = [ArticleGetAllResponse.model_validate(_nest_row(row)) for row in rows]
        return Page(items=items, total=total or 0, page=page, size=size)

    async def search_articles(
        self, query: str, filters: ArticleFilters, *, page: int, size: int
    ) -> Page[ArticleSearchResult]:
        """Ranked full-text search over the articles the reader may see; same filters as ``list_articles``."""

        skip, limit = paginate(page, size)
        rows, total = await self.repository.search_articles(query, filters, skip=skip, limit=limit)
        items = [ArticleSearchResult.model_validate(_nest_row(row)) for row in rows]
        return Page(items=items, total=total, page=page, size=size)
