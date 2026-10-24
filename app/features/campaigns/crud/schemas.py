"""Request/response schemas of campaign CRUD."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import CampaignCharacterStatus, CampaignStatus
from app.features.campaigns.schemas import CampaignText, CampaignTitle, PublicCampaignBrief, UserBrief, ViewerRole


class CampaignCreate(BaseModel):
    """
    ``POST /campaigns``. With ``public_campaign_id`` the campaign is made from that preset: an omitted ``title`` /
    ``description_markdown`` is copied from it (articles are not copied, the preset keeps pointing to them).
    """

    title: CampaignTitle | None = None
    description_markdown: CampaignText | None = None
    public_campaign_id: int | None = None
    status: CampaignStatus = CampaignStatus.PLANNING

    @model_validator(mode="after")
    def _title_or_preset(self) -> "CampaignCreate":
        """A campaign made from scratch needs its own title."""

        if self.title is None and self.public_campaign_id is None:
            raise ValueError("title is required unless the campaign is created from a public campaign")

        return self


class CampaignUpdate(BaseModel):
    """
    ``PATCH /campaigns/{id}`` (only sent fields change). ``public_campaign_id: null`` unlinks the preset.

    Moving ``status`` to ``finished``/``abandoned`` releases the campaign's active characters (``retired``).
    """

    title: CampaignTitle | None = None
    description_markdown: CampaignText | None = None
    status: CampaignStatus | None = None
    public_campaign_id: int | None = None

    @model_validator(mode="after")
    def _no_null_fields(self) -> "CampaignUpdate":
        """Only ``public_campaign_id`` may be sent as ``null``."""

        for field in ("title", "description_markdown", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class MyCampaignCharacter(BaseModel):
    """One of the caller's own characters in the campaign (participation not ``removed``): the player's side."""

    participation_id: int
    character_id: int
    name: str
    status: CampaignCharacterStatus


class CampaignListItem(BaseModel):
    """A row of ``GET /campaigns``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: CampaignStatus
    #: ``null`` once the GM's account was deleted (the campaign stays).
    owner: UserBrief | None = None
    public_campaign: PublicCampaignBrief | None = None
    viewer_role: ViewerRole
    updated_at: datetime
    archived_at: datetime | None = None
    #: The caller's characters at this table (empty for a GM who doesn't play in it).
    my_characters: list[MyCampaignCharacter] = Field(default_factory=list)


class CampaignResponse(CampaignListItem):
    """One campaign. For players ``description_markdown`` comes without ``:::gm`` blocks."""

    description_markdown: str
    created_at: datetime
