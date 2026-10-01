"""Request/response schemas for the article relations endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.constants import RELATION_TYPES, ArticleVisibility
from app.features.articles.crud.schemas import ArticleBrief
from app.features.articles.schema_validators import reject_explicit_null, reject_nested_gm_containers, validate_in_list

#: ``article_relations.note`` is ``String(300)``.
NOTE_MAX_LENGTH = 300

RelationType = Annotated[str, AfterValidator(lambda value: validate_in_list(value, RELATION_TYPES, "relation_type"))]
RelationNote = Annotated[str, Field(max_length=NOTE_MAX_LENGTH), AfterValidator(reject_nested_gm_containers)]


class ArticleRelationCreate(BaseModel):
    """Payload to link the source article (path id) to another article."""

    to_article_id: int
    relation_type: RelationType
    note: RelationNote | None = None
    visibility: ArticleVisibility = ArticleVisibility.PUBLIC


class ArticleRelationUpdate(BaseModel):
    """
    PATCH payload: only provided fields change. The two linked articles and the
    direction are fixed — to relink, delete the relation and create a new one.
    """

    relation_type: RelationType | None = None
    note: RelationNote | None = None
    visibility: ArticleVisibility | None = None

    @field_validator("relation_type", "visibility")
    def validate_not_null(cls, value, info):
        """``relation_type``/``visibility`` are NOT NULL columns — reject an explicit ``null`` (422, not 500)."""

        return reject_explicit_null(value, info.field_name)


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
