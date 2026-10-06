"""Article version history endpoints (mounted under ``/articles/{article_id}``)."""

from typing import Any

from fastapi import APIRouter, Query

from app.core.pagination import CursorPage, CursorQuery, Page, PaginationQuery, use_cursor
from app.features.articles.access import ArticleActor
from app.features.articles.crud.schemas import ArticleResponse
from app.features.articles.dependencies import ArticleCrudDep, ArticleRevisionsDep
from app.features.articles.revisions.schemas import (
    ArticleRevisionBrief,
    ArticleRevisionDiff,
    ArticleRevisionResponse,
)
from app.features.auth.dependencies import GmUserDep

router = APIRouter()

REVISION_404: dict[int | str, dict[str, Any]] = {404: {"description": "No such article, or it has no such version."}}


@router.get(
    "/revisions",
    response_model=Page[ArticleRevisionBrief] | CursorPage[ArticleRevisionBrief],
    summary="List an article's versions",
    responses={404: {"description": "No article exists with the given ID."}, 422: {"description": "Invalid `cursor`."}},
)
async def list_article_revisions(
    article_id: int,
    revisions: ArticleRevisionsDep,
    _: GmUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    pagination: PaginationQuery = "page",
    cursor: CursorQuery = None,
):
    """
    Return the article's history, newest version first (`version`, `title`, who saved it, `change_note`, when).
    Offset `Page` by default, keyset `CursorPage` with `pagination=cursor`.
    **GM only** (any GM may read any article's history, like its drafts).
    """

    return await revisions.list_revisions(
        article_id, page=page, size=size, cursor=cursor, use_cursor=use_cursor(pagination, cursor)
    )


@router.get(
    "/revisions/{version}",
    response_model=ArticleRevisionResponse,
    summary="Get one version of an article",
    responses=REVISION_404,
)
async def get_article_revision(article_id: int, version: int, revisions: ArticleRevisionsDep, _: GmUserDep):
    """Return the full content of one version, `:::gm` blocks included. **GM only.**"""

    return await revisions.get_revision(article_id, version)


@router.get(
    "/revisions/{version}/diff",
    response_model=ArticleRevisionDiff,
    summary="Compare a version with another",
    responses=REVISION_404,
)
async def diff_article_revision(
    article_id: int,
    version: int,
    revisions: ArticleRevisionsDep,
    _: GmUserDep,
    against: int | None = Query(None, ge=1, description="Version to compare with; default: the previous one."),
):
    """
    Show what `version` changed relative to `against` (default: the previous version; version 1 is compared with an
    empty article): the changed scalar fields and a unified diff of `body_markdown`. **GM only.**
    """

    return await revisions.diff(article_id, version, against)


@router.post(
    "/revisions/{version}/restore",
    response_model=ArticleResponse,
    summary="Restore an old version of an article",
    responses={
        **REVISION_404,
        403: {"description": "The article was written by another GM."},
    },
)
async def restore_article_revision(article_id: int, version: int, article_service: ArticleCrudDep, gm_user: GmUserDep):
    """
    Make the content of `version` current again as a **new** version (history is kept). **Author or founder only.**

    Restores content only (title, excerpt, body, type, subtype, visibility); `status`, `slug` and the position in the
    tree stay as they are.
    """

    return await article_service.restore_revision(article_id, version, ArticleActor.of(gm_user))
