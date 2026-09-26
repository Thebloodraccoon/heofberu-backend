"""Request/response schemas for the article relations endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import RELATION_TYPES, ArticleVisibility
from app.features.articles.crud.schemas import ArticleBrief


def _validate_relation_type(relation_type: str) -> str:
    """Reject a ``relation_type`` not in the open ``RELATION_TYPES`` list."""

    if relation_type not in RELATION_TYPES:
        raise ValueError(f"relation_type must be one of {RELATION_TYPES}")

    return relation_type


class ArticleRelationCreate(BaseModel):
    """Payload to link the source article (path id) to another article."""

    to_article_id: int
    relation_type: str
    note: str | None = None
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC

    @field_validator("relation_type")
    def validate_relation_type(cls, relation_type):
        """Reject a ``relation_type`` not in the open ``RELATION_TYPES`` list."""

        return _validate_relation_type(relation_type)


class ArticleRelationUpdate(BaseModel):
    """
    PATCH payload: only provided fields change. The two linked articles and the
    direction are fixed — to relink, delete the relation and create a new one.
    """

    relation_type: str | None = None
    note: str | None = None
    visibility: ArticleVisibility | None = None

    @field_validator("relation_type", "visibility")
    def reject_explicit_null(cls, value, info):
        """``relation_type``/``visibility`` are NOT NULL columns — reject an explicit ``null`` (422, not 500)."""

        if value is None:
            raise ValueError(f"{info.field_name} may not be null")

        return value

    @field_validator("relation_type")
    def validate_relation_type(cls, relation_type):
        """Reject a ``relation_type`` not in the open ``RELATION_TYPES`` list."""

        return _validate_relation_type(relation_type)


class ArticleRelationResponse(BaseModel):
    """
    One relation as seen from a given article: the *other* article plus
    which way the relation points relative to it (``direction="outgoing"``
    when this article is ``from_article``, ``"incoming"`` when it's
    ``to_article``) — lets a client render "this article MENTIONS X" vs
    "Y MENTIONS this article" without inspecting raw FK columns.
    """

    id: int
    relation_type: str
    note: str | None = None
    visibility: ArticleVisibility
    created_at: datetime
    direction: Literal["outgoing", "incoming"]
    article: ArticleBrief

    model_config = ConfigDict(from_attributes=True)
