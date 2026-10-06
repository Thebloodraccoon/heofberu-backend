"""Article tree endpoints: children, descendants, ancestors (all open, visibility-filtered)."""

from typing import Any

from fastapi import APIRouter

from app.features.articles.crud.schemas import ArticleBrief
from app.features.articles.dependencies import ArticleTreeDep
from app.features.auth.dependencies import OptionalUserDep, can_see_hidden

router = APIRouter()

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Article not found (or not visible to the caller)."}}


@router.get(
    "/{article_id:int}/children",
    response_model=list[ArticleBrief],
    summary="List an article's direct children",
    responses=NOT_FOUND,
)
async def get_article_children(article_id: int, tree: ArticleTreeDep, user: OptionalUserDep):
    """Return the visible articles whose `parent_id` is this one (one level down only). Open endpoint."""

    return await tree.get_children(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/{article_id:int}/descendants",
    response_model=list[ArticleBrief],
    summary="List every descendant of an article",
    responses=NOT_FOUND,
)
async def get_article_descendants(article_id: int, tree: ArticleTreeDep, user: OptionalUserDep):
    """Return every visible article under this one in the `parent_id`/`path` tree, at any depth. Open endpoint."""

    return await tree.get_descendants(article_id, include_hidden=can_see_hidden(user))


@router.get(
    "/{article_id:int}/ancestors",
    response_model=list[ArticleBrief],
    summary="List an article's ancestor chain (breadcrumbs)",
    responses=NOT_FOUND,
)
async def get_article_ancestors(article_id: int, tree: ArticleTreeDep, user: OptionalUserDep):
    """Return the chain of visible parents above this article, root-first (for breadcrumbs). Open endpoint."""

    return await tree.get_ancestors(article_id, include_hidden=can_see_hidden(user))
