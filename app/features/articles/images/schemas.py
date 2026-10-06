"""Response schema for the article image endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArticleImageResponse(BaseModel):
    """One uploaded article image as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    image_url: str
    created_at: datetime
