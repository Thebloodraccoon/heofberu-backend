"""Request/response schemas for the article CRUD endpoints (identity/content fields; tags/images live in their own folders)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ARTICLE_TYPES, ArticleStatus, ArticleVisibility
from app.features.articles.images.schemas import ArticleImageResponse
from app.features.articles.schema_validators import reject_explicit_null, validate_in_list
from app.features.shared.tags.schemas import TagBrief


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

        return validate_in_list(article_type, ARTICLE_TYPES, "article_type")


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
    def validate_not_null(cls, value, info):
        """
        NOT NULL columns on ``Article`` would otherwise fail later as an uncaught ``IntegrityError``
        (500) in ``ArticleRepository.apply_update`` — Pydantic only skips this for an UNSET field
        (PATCH semantics), not an explicit ``null``.
        """

        return reject_explicit_null(value, info.field_name)

    @field_validator("article_type")
    def validate_article_type(cls, article_type):
        """Reject an ``article_type`` not in the open ``ARTICLE_TYPES`` list."""

        return validate_in_list(article_type, ARTICLE_TYPES, "article_type")


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
