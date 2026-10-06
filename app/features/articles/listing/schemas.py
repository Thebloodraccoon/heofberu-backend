"""Response rows of ``GET /articles`` and ``GET /articles/search``."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import ArticleStatus, ArticleVisibility
from app.features.articles.crud.schemas import ArticleAuthorBrief, ArticleSubtypeBrief


class ArticleGetAllResponse(BaseModel):
    """Lightweight listing row (no body, tags or images)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    excerpt: str | None = None
    article_type: str
    subtype: ArticleSubtypeBrief | None = None
    status: ArticleStatus
    visibility: ArticleVisibility
    author: ArticleAuthorBrief | None = None
    pending_proposals: int | None = Field(
        default=None, description="Change proposals awaiting a decision (GM only; null for other readers)."
    )


class ArticleSearchResult(ArticleGetAllResponse):
    """
    One ``GET /articles/search`` hit: listing fields plus relevance ``rank`` and a body ``snippet``.

    ``snippet`` wraps matched terms in ``<mark>``; everything else in it is raw markdown, so escape it before rendering.
    """

    rank: float
    snippet: str | None = None
