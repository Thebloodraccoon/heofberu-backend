"""Request/response schemas for proposed article changes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.constants import ArticleProposalStatus, ArticleVisibility
from app.features.articles.crud.schemas import (
    CHANGE_NOTE_MAX_LENGTH,
    ArticleBody,
    ArticleExcerpt,
    ArticleTitle,
    ArticleType,
)


class ProposalArticleRef(BaseModel):
    """The article a proposal targets, enough to link to it from a review queue."""

    id: int
    title: str
    slug: str


class ArticleProposalBrief(BaseModel):
    """One proposal in a list: who proposed what against which version, and how it was reviewed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    article: ProposalArticleRef | None = None
    base_version: int
    proposer_id: int | None = None
    title: str
    change_note: str | None = None
    status: ArticleProposalStatus
    is_stale: bool = Field(
        default=False,
        description="Pending, but the article moved past `base_version`: rebase it before accepting.",
    )
    reviewer_id: int | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    accepted_version: int | None = None
    created_at: datetime


class ArticleProposalResponse(ArticleProposalBrief):
    """The full proposed content (``:::gm`` blocks included: GM-only endpoints)."""

    excerpt: str | None = None
    body_markdown: str
    article_type: str
    subtype_id: int | None = None
    visibility: ArticleVisibility


class ArticleProposalReject(BaseModel):
    """Optional body of a rejection."""

    reason: str | None = Field(default=None, max_length=300, description="Why it was rejected (shown to the proposer).")


class ArticleProposalReplace(BaseModel):
    """
    Full new content of a pending proposal (e.g. a resolved merge conflict). ``base_version`` must be the
    article's current version.
    """

    base_version: int = Field(ge=1)
    title: ArticleTitle
    excerpt: ArticleExcerpt | None = None
    body_markdown: ArticleBody = ""
    article_type: ArticleType
    subtype_id: int | None = None
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC
    change_note: str | None = Field(default=None, max_length=CHANGE_NOTE_MAX_LENGTH)
