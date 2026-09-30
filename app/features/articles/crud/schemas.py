"""Request/response schemas for the article CRUD endpoints (identity/content fields; tags/images live in their own folders)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ARTICLE_TYPES, ArticleStatus, ArticleVisibility
from app.features.articles.images.schemas import ArticleImageResponse
from app.features.shared.tags.schemas import TagBrief


def _validate_article_type(article_type: str) -> str:
    """Reject an ``article_type`` not in the open ``ARTICLE_TYPES`` list."""

    if article_type not in ARTICLE_TYPES:
        raise ValueError(f"article_type must be one of {ARTICLE_TYPES}")

    return article_type


class ArticleSubtypeBrief(BaseModel):
    """Subtype reference embedded in article responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ArticleBase(BaseModel):
    """Base article fields shared by create, update, and response schemas."""

    title: str = Field(max_length=200)
    excerpt: str | None = Field(default=None, max_length=500)
    body_markdown: str = ""
    article_type: str
    subtype_id: int | None = Field(
        default=None,
        description="An `/articles/subtypes` entry of this article's own `article_type` (location → таверна).",
    )
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC
    parent_id: int | None = None

    @field_validator("article_type")
    def validate_article_type(cls, article_type):
        """Reject an ``article_type`` not in the open ``ARTICLE_TYPES`` list."""

        return _validate_article_type(article_type)


class ArticleCreate(ArticleBase):
    """
    Create payload for an article: identity/content fields only.

    ``slug`` is not client-supplied: it is generated from ``title`` (transliterated,
    made unique with a ``-2``/``-3`` suffix) and stays stable across later renames.
    ``status`` starts at ``DRAFT`` and ``tags``/``images`` are attached
    afterwards through their own capability endpoints (mirrors ``RaceCreate``).
    """


class ArticleUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    ``status`` is not here: it moves only through the review workflow endpoints
    (``ArticleCrudService.transition``).
    """

    title: str | None = Field(default=None, max_length=200)
    excerpt: str | None = Field(default=None, max_length=500)
    body_markdown: str | None = None
    article_type: str | None = None
    subtype_id: int | None = None
    parent_id: int | None = None
    visibility: ArticleVisibility | None = None

    @field_validator("title", "body_markdown", "article_type", "visibility")
    def reject_explicit_null(cls, value, info):
        """
        Reject an explicit ``null`` for a field that's ``nullable=False`` on the ``Article``
        model — without this, it passes Pydantic (the field is ``X | None`` for PATCH
        semantics) and only fails later as an uncaught ``IntegrityError`` (500) when
        ``ArticleRepository.apply_update`` sets the column to ``NULL``.

        Only runs when the field is actually present in the payload — Pydantic v2
        skips validators for unset fields that fall back to their ``None`` default.
        """

        if value is None:
            raise ValueError(f"{info.field_name} may not be null")

        return value

    @field_validator("article_type")
    def validate_article_type(cls, article_type):
        """Reject an ``article_type`` not in the open ``ARTICLE_TYPES`` list."""

        return _validate_article_type(article_type)


class ArticleResponse(ArticleBase):
    """Full article representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    status: ArticleStatus
    author_id: int | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    subtype: ArticleSubtypeBrief | None = None
    tags: list[TagBrief] = []
    images: list[ArticleImageResponse] = []


class ArticleGetAllResponse(BaseModel):
    """Lightweight listing row returned by the paginated ``GET /articles`` endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    excerpt: str | None = None
    article_type: str
    subtype: ArticleSubtypeBrief | None = None
    status: ArticleStatus
    visibility: ArticleVisibility


class ArticleSearchResult(ArticleGetAllResponse):
    """One ``GET /articles/search`` hit: listing fields plus relevance ``rank`` and a body ``snippet``.

    ``snippet`` wraps matched terms in ``<mark>``; everything else in it is raw markdown, so escape it before rendering.
    """

    rank: float
    snippet: str | None = None


class ArticleBrief(BaseModel):
    """Minimal article reference embedded in relation/tree responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    article_type: str
    subtype: ArticleSubtypeBrief | None = None
