"""Schemas of public campaigns: CRUD, article links, showcase and reviews."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.constants import CAMPAIGN_PITCH_MAX_LENGTH, PublicCampaignStatus
from app.features.campaigns.schemas import CampaignText, CampaignTitle, UserBrief

Pitch = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CAMPAIGN_PITCH_MAX_LENGTH)]

#: Upper bound on tag ids / article links sent in one request.
MAX_LINKS = 100


class TagBrief(BaseModel):
    """A tag of the shared dictionary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PublicCampaignCreate(BaseModel):
    """``POST /public-campaigns`` (created as a draft)."""

    title: CampaignTitle
    pitch: Pitch = ""
    description_markdown: CampaignText = ""
    tag_ids: list[int] = Field(default_factory=list, max_length=MAX_LINKS)


class PublicCampaignUpdate(BaseModel):
    """``PATCH``: only sent fields change, none may be ``null``. ``tag_ids`` replaces the whole tag set."""

    title: CampaignTitle | None = None
    pitch: Pitch | None = None
    description_markdown: CampaignText | None = None
    tag_ids: list[int] | None = Field(default=None, max_length=MAX_LINKS)

    @model_validator(mode="after")
    def _no_null_fields(self) -> "PublicCampaignUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class PublicCampaignListItem(BaseModel):
    """A catalog row."""

    id: int
    slug: str
    title: str
    pitch: str
    status: PublicCampaignStatus
    author: UserBrief | None = None
    tags: list[TagBrief] = []
    #: How many game campaigns were made from it (social proof for the catalog).
    campaign_count: int = 0
    published_at: datetime | None = None
    updated_at: datetime


class PublicCampaignArticleLink(BaseModel):
    """One article a public campaign points GMs to."""

    article_id: int
    slug: str
    title: str
    article_type: str
    position: int
    note: str | None = None


class PublicCampaignResponse(PublicCampaignListItem):
    """
    One public campaign. Non-GMs get ``description_markdown`` without ``:::gm`` blocks and no ``articles``
    (``null``): the article links are for GMs.
    """

    description_markdown: str
    created_at: datetime
    articles: list[PublicCampaignArticleLink] | None = None


class PublicCampaignArticleEntry(BaseModel):
    """One link in ``PUT /public-campaigns/{id}/articles``; ``position`` defaults to the list order."""

    article_id: int
    position: int | None = Field(default=None, ge=0, le=10_000)
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class PublicCampaignArticlesUpdate(BaseModel):
    """Full replacement of a public campaign's article links."""

    articles: list[PublicCampaignArticleEntry] = Field(max_length=MAX_LINKS)


class PublicCampaignReview(BaseModel):
    """A player's review of one of the game campaigns made from this public campaign."""

    id: int
    author: UserBrief
    body: str
    created_at: datetime
    edited_at: datetime | None = None
