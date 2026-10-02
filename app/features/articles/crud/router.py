"""Article endpoints: listing/search, tree navigation, get-by-id/slug, create, update, review workflow, delete."""

from typing import Annotated, Literal

from fastapi import APIRouter, Body, Query, status
from pydantic import StringConstraints

from app.constants import ArticleStatus
from app.core.pagination import CursorPage, CursorQuery, Page, PaginationQuery, use_cursor
from app.features.articles.access import ArticleActor
from app.features.articles.crud.schemas import (
    ArticleBrief,
    ArticleCreate,
    ArticleGetAllResponse,
    ArticleResponse,
    ArticleSearchResult,
    ArticleUpdate,
)
from app.features.articles.dependencies import ArticleCrudDep
from app.features.auth.dependencies import FounderDep, GmUserDep, OptionalUserDep, can_see_hidden

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


@router.get(
    "",
    response_model=Page[ArticleGetAllResponse] | CursorPage[ArticleGetAllResponse],
    summary="List articles",
    responses={422: {"description": "Invalid `cursor`, or one issued for a different `sort`."}},
)
async def get_articles(
    article_service: ArticleCrudDep,
    user: OptionalUserDep,
    status_filter: Annotated[
        list[ArticleStatus] | None,
        Query(
            alias="status",
            description="GM only in effect (non-GMs only ever see `published`). Repeat the key: "
            "`?status=in_review` is the review queue, `?status=published&sort=newest` the latest articles.",
        ),
    ] = None,
    tag_id: TagIdsQuery = None,
    tag_match: TagMatchQuery = "any",
    article_type: ArticleTypesQuery = None,
    subtype_ids: SubtypeQuery = None,
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

    return await article_service.list_articles(
        page=page,
        size=size,
        include_hidden=can_see_hidden(user),
        statuses=status_filter,
        article_types=article_type,
        subtype_ids=subtype_ids,
        tag_ids=tag_id,
        match_all_tags=tag_match == "all",
        sort=sort,
        cursor=cursor,
        use_cursor=use_cursor(pagination, cursor),
    )


@router.get(
    "/search",
    response_model=Page[ArticleSearchResult],
    summary="Full-text search articles",
)
async def search_articles(
    article_service: ArticleCrudDep,
    user: OptionalUserDep,
    q: str = Query(
        ...,
        min_length=2,
        max_length=200,
        description='Search text; supports `"phrases"`, `-exclude` and `or`.',
    ),
    tag_id: TagIdsQuery = None,
    tag_match: TagMatchQuery = "any",
    article_type: ArticleTypesQuery = None,
    subtype_ids: SubtypeQuery = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=50, description="Page size"),
):
    """
    Ranked full-text search over title (highest weight), excerpt and body, with Russian
    stemming plus literal matching, and typo-tolerant matching on the title. Each hit carries
    a `rank` and a body `snippet` with matches wrapped in `<mark>` (the rest of the snippet is
    raw markdown — escape it before rendering). Same visibility rules as the list endpoint.
    Open endpoint.
    """

    return await article_service.search_articles(
        q,
        page=page,
        size=size,
        include_hidden=can_see_hidden(user),
        article_types=article_type,
        subtype_ids=subtype_ids,
        tag_ids=tag_id,
        match_all_tags=tag_match == "all",
    )


@router.get(
    "/{article_id:int}",
    response_model=ArticleResponse,
    summary="Get an article by ID",
    responses={
        404: {"description": "Article not found (or not visible to the caller)."},
    },
)
async def get_article(article_id: int, article_service: ArticleCrudDep, user: OptionalUserDep):
    """
    Return a single article by ID, with everything about it: base fields, tags and images.
    Drafts and GM-only articles 404 for non-GMs, and `:::gm ... :::` blocks are stripped from
    `body_markdown` for them. Open endpoint.
    """

    return await article_service.get_article(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/by-slug/{slug}",
    response_model=ArticleResponse,
    summary="Get an article by slug",
    responses={
        404: {"description": "Article not found (or not visible to the caller)."},
    },
)
async def get_article_by_slug(slug: str, article_service: ArticleCrudDep, user: OptionalUserDep):
    """Same as `GET /articles/{article_id}`, looked up by the article's `slug`. Open endpoint."""

    return await article_service.get_article_by_slug(slug, include_hidden=can_see_hidden(user))


@router.get(
    "/{article_id:int}/children",
    response_model=list[ArticleBrief],
    summary="List an article's direct children",
    responses={404: {"description": "Article not found (or not visible to the caller)."}},
)
async def get_article_children(article_id: int, article_service: ArticleCrudDep, user: OptionalUserDep):
    """Return the visible articles whose `parent_id` is this one (one level down only). Open endpoint."""

    return await article_service.get_children(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/{article_id:int}/descendants",
    response_model=list[ArticleBrief],
    summary="List every descendant of an article",
    responses={404: {"description": "Article not found (or not visible to the caller)."}},
)
async def get_article_descendants(article_id: int, article_service: ArticleCrudDep, user: OptionalUserDep):
    """Return every visible article under this one in the `parent_id`/`path` tree, at any depth. Open endpoint."""

    return await article_service.get_descendants(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/{article_id:int}/ancestors",
    response_model=list[ArticleBrief],
    summary="List an article's ancestor chain (breadcrumbs)",
    responses={404: {"description": "Article not found (or not visible to the caller)."}},
)
async def get_article_ancestors(article_id: int, article_service: ArticleCrudDep, user: OptionalUserDep):
    """Return the chain of visible parents above this article, root-first (for breadcrumbs). Open endpoint."""

    return await article_service.get_ancestors(article_id, include_hidden=can_see_hidden(user))


@router.post(
    "",
    response_model=ArticleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an article",
    responses={
        400: {"description": "parent_id/subtype_id doesn't exist or the subtype belongs to another article_type."},
    },
)
async def create_article(
    data: Annotated[
        ArticleCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Minimal lore entry",
                    "value": {"title": "Khazad-dum", "article_type": "location"},
                },
                "child_of_region": {
                    "summary": "Location nested under a region",
                    "value": {
                        "title": "Moria",
                        "article_type": "location",
                        "subtype_id": 3,
                        "parent_id": 12,
                        "body_markdown": "A once-great dwarven kingdom...\n\n:::gm\nA Balrog sleeps below.\n:::",
                    },
                },
            },
        ),
    ],
    article_service: ArticleCrudDep,
    gm_user: GmUserDep,
):
    """
    Create a new article. **GM only.**

    Identity/content fields only — `tags` are attached afterwards through
    `PUT /articles/{article_id}/tags`. `slug` is generated from the title (never sent by the client), `status`
    starts at `DRAFT`, `author_id` is the calling GM, and `path` is derived server-side from `parent_id`.

    The title is trimmed and may not be blank. A `:::gm` block in `excerpt`/`body_markdown` must be flat: it
    may not contain another `:::` container (422); close it with `:::` first.
    """

    return await article_service.create_article(data, gm_user.id)


@router.patch(
    "/{article_id:int}",
    response_model=ArticleResponse,
    summary="Update an article's fields",
    responses={
        400: {
            "description": "parent_id doesn't exist, would make the article its own ancestor or nest the tree "
            "too deeply, or subtype_id doesn't fit the article_type."
        },
        404: {"description": "No article exists with the given ID."},
    },
)
async def update_article(
    article_id: int,
    data: Annotated[
        ArticleUpdate,
        Body(
            openapi_examples={
                "rewrite": {
                    "summary": "Edit title and body",
                    "value": {"title": "Khazad-dum, the Dwarrowdelf", "body_markdown": "Updated lore text..."},
                },
                "reparent": {
                    "summary": "Move under a different parent",
                    "value": {"parent_id": 12},
                },
            }
        ),
    ],
    article_service: ArticleCrudDep,
    gm_user: GmUserDep,
):
    """
    Partially update an article's fields. **Author or founder only** (403 for another GM).

    Only fields included in the request body are changed; use
    `PUT /articles/{article_id}/tags` for tags. Including `parent_id`
    re-roots `path` for this article and its whole existing subtree. `status` can't be
    changed here — use the `submit`/`publish`/`reject`/`archive`/`restore` actions. The author may edit their
    article in any status, a published one included (it stays published); the founder may edit any article;
    same title/`:::gm` rules as on create.

    Every change of the content fields (title, excerpt, body, type, subtype, visibility) is saved as a new
    version (`version` in the response; history under `/articles/{article_id}/revisions`). The optional
    `change_note` is stored with that version.
    """

    return await article_service.update_article(article_id, data, ArticleActor.of(gm_user))


@router.delete(
    "/{article_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an article",
    responses={
        404: {"description": "No article exists with the given ID."},
    },
)
async def delete_article(article_id: int, article_service: ArticleCrudDep, _: FounderDep):
    """
    Delete an article. **Founder only.**

    Child articles (`parent_id` pointing at this one) are detached, not
    deleted (`ondelete="SET NULL"`); its tag links and relations are
    removed (cascade).
    """

    await article_service.delete(article_id)
    return None


TRANSITION_RESPONSES = {
    403: {"description": "`submit` by a GM who isn't the author."},
    404: {"description": "No article exists with the given ID."},
    409: {
        "description": "The action isn't allowed from the article's current status, or (`publish`) the article was edited after the `version` you reviewed."
    },
}


@router.post(
    "/{article_id:int}/submit",
    response_model=ArticleResponse,
    summary="Send a draft for review",
    responses=TRANSITION_RESPONSES,
)
async def submit_article(article_id: int, article_service: ArticleCrudDep, gm_user: GmUserDep):
    """`draft` → `in_review`. **Author or founder only** (403 for another GM)."""

    return await article_service.transition(article_id, "submit", actor=ArticleActor.of(gm_user))


@router.post(
    "/{article_id:int}/publish",
    response_model=ArticleResponse,
    summary="Approve and publish an article under review",
    responses=TRANSITION_RESPONSES,
)
async def publish_article(
    article_id: int,
    article_service: ArticleCrudDep,
    founder: FounderDep,
    version: int = Query(
        ...,
        ge=1,
        description="The `version` of the article you reviewed. Publishing fails with 409 if it was edited since.",
    ),
):
    """
    `in_review` → `published`; records the reviewer, the first publish stamps `published_at`. **Founder only.**

    Pass the `version` you reviewed (`GET /articles/{id}`, changes via `GET /articles/{id}/revisions/{version}/diff`):
    if the author edited the article after that, the response is 409 and nothing is published.
    """

    return await article_service.transition(
        article_id, "publish", actor=ArticleActor.of(founder), expected_version=version
    )


@router.post(
    "/{article_id:int}/reject",
    response_model=ArticleResponse,
    summary="Send an article under review back to draft",
    responses=TRANSITION_RESPONSES,
)
async def reject_article(article_id: int, article_service: ArticleCrudDep, founder: FounderDep):
    """`in_review` → `draft`; records the reviewer. **Founder only.**"""

    return await article_service.transition(article_id, "reject", actor=ArticleActor.of(founder))


@router.post(
    "/{article_id:int}/archive",
    response_model=ArticleResponse,
    summary="Archive an article",
    responses=TRANSITION_RESPONSES,
)
async def archive_article(article_id: int, article_service: ArticleCrudDep, founder: FounderDep):
    """`draft` / `in_review` / `published` → `archived` (hidden from non-GMs). **Founder only.**"""

    return await article_service.transition(article_id, "archive", actor=ArticleActor.of(founder))


@router.post(
    "/{article_id:int}/restore",
    response_model=ArticleResponse,
    summary="Restore an archived article to draft",
    responses=TRANSITION_RESPONSES,
)
async def restore_article(article_id: int, article_service: ArticleCrudDep, founder: FounderDep):
    """`archived` → `draft`. **Founder only.**"""

    return await article_service.transition(article_id, "restore", actor=ArticleActor.of(founder))
