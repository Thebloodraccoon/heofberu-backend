"""Response schemas for the article version history endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.constants import ArticleVisibility


class ArticleRevisionBrief(BaseModel):
    """One history row: who saved which version, when, and why."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    title: str
    editor_id: int | None = None
    change_note: str | None = None
    created_at: datetime


class ArticleRevisionResponse(ArticleRevisionBrief):
    """A full snapshot of the article's content at that version (``:::gm`` blocks included: GM-only endpoint)."""

    excerpt: str | None = None
    body_markdown: str
    article_type: str
    subtype_id: int | None = None
    visibility: ArticleVisibility


class FieldChange(BaseModel):
    """A scalar field's value in the two compared versions."""

    old: str | int | None = None
    new: str | int | None = None


class ArticleRevisionDiff(BaseModel):
    """What changed from version ``against`` to ``version``: changed scalar fields plus a unified diff of the body."""

    version: int
    against: int
    fields: dict[str, FieldChange]
    body_diff: str
