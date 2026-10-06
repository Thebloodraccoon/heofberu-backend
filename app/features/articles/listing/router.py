"""Article listing endpoints: ``GET /articles`` and ``GET /articles/search``, sharing one filter dependency."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import StringConstraints

from app.constants import ArticleStatus
from app.core.pagination import CursorPage, CursorQuery, Page, PaginationQuery, use_cursor
from app.features.articles.dependencies import ArticleListingDep
from app.features.articles.listing.filters import ArticleFilters
from app.features.articles.listing.schemas import ArticleGetAllResponse, ArticleSearchResult
from app.features.auth.dependencies import OptionalUserDep, can_see_hidden

router = APIRouter()

#: Upper bound on the repeated filter keys of the open list/search endpoints (each becomes an ``IN (...)`` entry).
MAX_FILTER_VALUES = 50

TagIdsQuery = Annotated[
    list[int] | None,
    Query(
        max_length=MAX_FILTER_VALUES,
        description="Tag ids (repeat the key: `?tag_id=3&tag_id=7`). See `tag_match` for any/all semantics.",
    ),
]
TagMatchQuery = Annotated[
    Literal["any", "all"],
    Query(description="`any` = article has at least one of the tags, `all` = it has every one of them."),
]
ArticleTypesQuery = Annotated[
    list[Annotated[str, StringConstraints(max_length=50)]] | None,
    Query(
        alias="article_type",
        max_length=MAX_FILTER_VALUES,
        description="Restrict to one or more article_type values (repeat the key: "
        "`?article_type=lore&article_type=npc`). See ARTICLE_TYPES. Omit for any type.",
    ),
]
StatusQuery = Annotated[
    list[ArticleStatus] | None,
    Query(
        alias="status",
        description="GM only in effect (non-GMs only ever see `published`). Repeat the key: "
        "`?status=in_review` is the review queue, `?status=published&sort=newest` the latest articles.",
    ),
]
HasPendingProposalsQuery = Annotated[
    bool | None,
    Query(
        description="GM only (ignored for others): `true` = articles with change proposals awaiting a decision "
        "(the proposals review queue), `false` = without.",
    ),
]
AuthorQuery = Annotated[
    int | None,
    Query(
        description="Only articles written by this user (`author_id`). Visibility still applies: non-GMs get only "
        "the author's published public articles.",
    ),
]
SubtypeQuery = Annotated[
    list[int] | None,
    Query(
        alias="subtype_id",
        max_length=MAX_FILTER_VALUES,
        description="Subtype ids (repeat the key; see `GET /articles/subtypes`). A subtype refines only its own "
        "type: `?article_type=location&article_type=npc&subtype_id=5` (5 = a location subtype) → those locations "
        "plus every NPC.",
    ),
]


def get_article_filters(
    user: OptionalUserDep,
    status_filter: StatusQuery = None,
    tag_id: TagIdsQuery = None,
    tag_match: TagMatchQuery = "any",
    article_type: ArticleTypesQuery = None,
    subtype_ids: SubtypeQuery = None,
    author_id: AuthorQuery = None,
    has_pending_proposals: HasPendingProposalsQuery = None,
) -> ArticleFilters:
    """The filter query parameters shared by list and search, plus the caller's visibility, as one value."""

    return ArticleFilters(
        include_hidden=can_see_hidden(user),
        statuses=tuple(status_filter or ()),
        article_types=tuple(article_type or ()),
        subtype_ids=tuple(subtype_ids or ()),
        tag_ids=tuple(tag_id or ()),
        match_all_tags=tag_match == "all",
        author_id=author_id,
        has_pending_proposals=has_pending_proposals,
    )


ArticleFiltersDep = Annotated[ArticleFilters, Depends(get_article_filters)]


@router.get(
    "",
    response_model=Page[ArticleGetAllResponse] | CursorPage[ArticleGetAllResponse],
    summary="List articles",
    responses={422: {"description": "Invalid `cursor`, or one issued for a different `sort`."}},
)
async def get_articles(
    listing: ArticleListingDep,
    filters: ArticleFiltersDep,
    sort: Literal["title", "newest", "oldest", "updated"] = Query(
        "title", description="`newest`/`oldest` order by published_at (falling back to created_at)."
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    pagination: PaginationQuery = "page",
    cursor: CursorQuery = None,
):
    """
    Return a paginated, filterable list of articles (listing-row fields only) — e.g. tag
    pages: `GET /articles?tag_id=3`. Anonymous callers and players only see `published`,
    `public` articles; GMs see everything. Response is `{items, total, page, size}`; with
    `pagination=cursor` (or a `cursor`) it is the keyset envelope `{items, next_cursor, size}`
    ordered by `(sort key, id)` (no `total`).
    Text search: `GET /articles/search`; direct children: `GET /articles/{id}/children`.
    Open endpoint.
    """

    return await listing.list_articles(
        filters, page=page, size=size, sort=sort, cursor=cursor, use_cursor=use_cursor(pagination, cursor)
    )


@router.get(
    "/search",
    response_model=Page[ArticleSearchResult],
    summary="Full-text search articles",
)
async def search_articles(
    listing: ArticleListingDep,
    filters: ArticleFiltersDep,
    q: str = Query(
        ...,
        min_length=2,
        max_length=200,
        description='Search text; supports `"phrases"`, `-exclude` and `or`.',
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=50, description="Page size"),
):
    """
    Ranked full-text search over title (highest weight), excerpt and body, with Russian
    stemming plus literal matching, and typo-tolerant matching on the title. Each hit carries
    a `rank` and a body `snippet` with matches wrapped in `<mark>` (the rest of the snippet is
    raw markdown — escape it before rendering). Same filters and visibility rules as the list endpoint.
    Open endpoint.
    """

    return await listing.search_articles(q, filters, page=page, size=size)
