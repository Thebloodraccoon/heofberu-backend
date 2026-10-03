"""
Article request/response schemas shared across the article capabilities.

Write payloads (``ArticleCreate`` / ``ArticleContentUpdate`` / ``ArticleUpdate``), the full ``ArticleResponse``,
and the embedded briefs (``ArticleBrief`` for tree/relation lists, author and subtype refs). Listing rows live in
``listing.schemas``.
"""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.constants import ARTICLE_TYPES, ArticleStatus, ArticleVisibility
from app.features.articles.images.schemas import ArticleImageResponse
from app.features.articles.schema_validators import (
    normalize_title,
    reject_explicit_null,
    reject_nested_gm_containers,
    validate_in_list,
)
from app.features.shared.tags.schemas import TagBrief

TITLE_MAX_LENGTH = 200
EXCERPT_MAX_LENGTH = 500
#: Upper bound on ``body_markdown`` (``Text`` column): far above real lore pages, far below the request-body cap.
BODY_MAX_LENGTH = 200_000
#: ``article_revisions.change_note`` is ``String(300)``.
CHANGE_NOTE_MAX_LENGTH = 300

ArticleType = Annotated[str, AfterValidator(lambda value: validate_in_list(value, ARTICLE_TYPES, "article_type"))]
ArticleTitle = Annotated[str, Field(max_length=TITLE_MAX_LENGTH), AfterValidator(normalize_title)]
ArticleExcerpt = Annotated[str, Field(max_length=EXCERPT_MAX_LENGTH), AfterValidator(reject_nested_gm_containers)]
ArticleBody = Annotated[str, Field(max_length=BODY_MAX_LENGTH), AfterValidator(reject_nested_gm_containers)]


class ArticleAuthorBrief(BaseModel):
    """Author reference embedded in article responses (public: shown to every reader of the article)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class ArticleSubtypeBrief(BaseModel):
    """Subtype reference embedded in article responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ArticleBase(BaseModel):
    """Article fields as stored and returned (no write-side validation, so legacy rows always serialize)."""

    title: str
    excerpt: str | None = None
    body_markdown: str = ""
    article_type: str
    subtype_id: int | None = Field(
        default=None,
        description="An `/articles/subtypes` entry of this article's own `article_type` (location → таверна).",
    )
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC
    parent_id: int | None = None


class ArticleCreate(BaseModel):
    """
    Create payload for an article: identity/content fields only.

    ``slug`` is not client-supplied: it is generated from ``title`` (transliterated,
    made unique with a ``-2``/``-3`` suffix) and stays stable across later renames.
    ``status`` starts at ``DRAFT`` and ``tags``/``images`` are attached
    afterwards through their own capability endpoints (mirrors ``RaceCreate``).

    ``title`` is trimmed and may not be blank; a ``:::gm`` block in ``excerpt``/``body_markdown`` may not
    contain another ``:::`` container.
    """

    title: ArticleTitle
    excerpt: ArticleExcerpt | None = None
    body_markdown: ArticleBody = ""
    article_type: ArticleType
    subtype_id: int | None = Field(
        default=None,
        description="An `/articles/subtypes` entry of this article's own `article_type` (location → таверна).",
    )
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC
    parent_id: int | None = None


class ArticleContentUpdate(BaseModel):
    """
    The versioned content fields, all optional (PATCH semantics); same rules as ``ArticleCreate``.

    Also the payload of a change proposal (``POST /articles/{id}/proposals``).
    """

    title: ArticleTitle | None = None
    excerpt: ArticleExcerpt | None = None
    body_markdown: ArticleBody | None = None
    article_type: ArticleType | None = None
    subtype_id: int | None = None
    visibility: ArticleVisibility | None = None
    change_note: str | None = Field(
        default=None,
        max_length=CHANGE_NOTE_MAX_LENGTH,
        description="Optional comment stored with the new version in the article history (not an article field).",
    )

    @field_validator("title", "body_markdown", "article_type", "visibility")
    def validate_not_null(cls, value, info):
        """
        NOT NULL columns on ``Article`` would otherwise fail later as an uncaught ``IntegrityError``
        (500) in the UPDATE — Pydantic only skips this for an UNSET field
        (PATCH semantics), not an explicit ``null``.
        """

        return reject_explicit_null(value, info.field_name)


class ArticleUpdate(ArticleContentUpdate):
    """
    Content fields plus ``parent_id`` — only provided fields are updated (PATCH semantics).

    ``status`` is not here: it moves only through the review workflow endpoints
    (``ArticleWorkflowService.transition``).
    """

    parent_id: int | None = None


class ArticleResponse(ArticleBase):
    """Full article representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    status: ArticleStatus
    author: ArticleAuthorBrief | None = None
    version: int | None = Field(
        default=None,
        description="Content version (GM/founder only; null for other readers, who always get the latest content).",
    )
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    subtype: ArticleSubtypeBrief | None = None
    tags: list[TagBrief] = []
    images: list[ArticleImageResponse] = []


class ArticleBrief(BaseModel):
    """Minimal article reference embedded in relation/tree responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    article_type: str
    subtype: ArticleSubtypeBrief | None = None
