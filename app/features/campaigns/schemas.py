"""Schemas shared by the campaign capabilities (brief nested objects and field types)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.constants import CAMPAIGN_REVIEW_MAX_LENGTH, CAMPAIGN_TEXT_MAX_LENGTH, CAMPAIGN_TITLE_MAX_LENGTH

CampaignTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CAMPAIGN_TITLE_MAX_LENGTH)
]
#: Markdown that may hold ``:::gm`` ... ``:::`` blocks, stripped for players.
CampaignText = Annotated[str, Field(max_length=CAMPAIGN_TEXT_MAX_LENGTH)]
ReviewText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CAMPAIGN_REVIEW_MAX_LENGTH)
]
ViewerRole = Literal["gm", "player"]


class UserBrief(BaseModel):
    """A user as shown inside campaigns: id and username only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class PublicCampaignBrief(BaseModel):
    """The public campaign a game campaign was made from."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
