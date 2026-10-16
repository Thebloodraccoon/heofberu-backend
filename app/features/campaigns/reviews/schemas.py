"""Schemas of player reviews: of a whole campaign (public) and of one session (for the GM)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.features.campaigns.schemas import ReviewText, UserBrief


class CampaignReviewWrite(BaseModel):
    """``PUT /campaigns/{id}/review``: the caller's review of the whole campaign (created or replaced)."""

    body: ReviewText


class SessionReviewWrite(BaseModel):
    """``PUT /campaigns/{id}/sessions/{sid}/review``. ``visible_to_table``: the rest of the table may read it too."""

    body: ReviewText
    visible_to_table: bool = False


class CampaignReviewResponse(BaseModel):
    """A campaign review. ``hidden_at`` is set only in the founder's view (others never get hidden reviews)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    author: UserBrief
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    hidden_at: datetime | None = None


class SessionReviewResponse(BaseModel):
    """A session review. ``hidden_at`` is set only in the founder's view (others never get hidden reviews)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    author: UserBrief
    body: str
    visible_to_table: bool
    created_at: datetime
    edited_at: datetime | None = None
    hidden_at: datetime | None = None
