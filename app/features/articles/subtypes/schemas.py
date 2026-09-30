"""Request/response schemas for the article subtype dictionary."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ARTICLE_TYPES
from app.features.articles.schema_validators import validate_in_list


def _normalize_name(name: str | None) -> str:
    """Trim and collapse inner whitespace; reject a blank (or explicit-null) name."""

    normalized = " ".join((name or "").split())
    if not normalized:
        raise ValueError("Subtype name must not be blank.")

    return normalized


class ArticleSubtypeCreate(BaseModel):
    """Payload for creating a subtype (GM only). Its ``article_type`` is fixed for good."""

    article_type: str
    name: str = Field(max_length=50)

    @field_validator("article_type")
    def validate_article_type(cls, article_type):
        """Reject an ``article_type`` not in ``ARTICLE_TYPES``."""

        return validate_in_list(article_type, ARTICLE_TYPES, "article_type")

    @field_validator("name")
    def normalize_name(cls, name):
        """Trim and collapse whitespace; reject a blank name."""

        return _normalize_name(name)


class ArticleSubtypeUpdate(BaseModel):
    """Rename only — a subtype's ``article_type`` never changes (its articles all share it)."""

    name: str | None = Field(default=None, max_length=50)

    @field_validator("name")
    def normalize_name(cls, name):
        """Trim and collapse whitespace; reject a blank or explicit-null name."""

        return _normalize_name(name)


class ArticleSubtypeResponse(BaseModel):
    """Full subtype representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    article_type: str
    name: str
