"""Schemas of campaign sessions: schedule, attendance and the chronicle."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.constants import CAMPAIGN_SESSION_MAX_ATTENDEES, CAMPAIGN_TITLE_MAX_LENGTH, CampaignSessionStatus
from app.features.campaigns.schemas import CampaignText, UserBrief, ViewerRole

SessionTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CAMPAIGN_TITLE_MAX_LENGTH)]


def as_utc(value: datetime | None) -> datetime | None:
    """A time without an offset is taken as UTC (the column is ``timestamptz``)."""

    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


SessionTime = Annotated[datetime, AfterValidator(as_utc)]


class CampaignSessionCreate(BaseModel):
    """``POST /campaigns/{id}/sessions``. ``number`` defaults to the next one."""

    number: int | None = Field(default=None, ge=1, le=100_000)
    title: SessionTitle = ""
    status: CampaignSessionStatus = CampaignSessionStatus.PLANNED
    scheduled_at: SessionTime | None = None
    chronicle_markdown: CampaignText = ""


class CampaignSessionUpdate(BaseModel):
    """``PATCH``: only sent fields change; ``scheduled_at`` may be ``null``."""

    number: int | None = Field(default=None, ge=1, le=100_000)
    title: SessionTitle | None = None
    status: CampaignSessionStatus | None = None
    scheduled_at: SessionTime | None = None
    chronicle_markdown: CampaignText | None = None

    @model_validator(mode="after")
    def _no_null_fields(self) -> "CampaignSessionUpdate":
        """Only ``scheduled_at`` may be sent as ``null``."""

        for field in ("number", "title", "status", "chronicle_markdown"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class SessionAttendanceUpdate(BaseModel):
    """``PUT /campaigns/{id}/sessions/{session_id}/attendance``: the full list of who attended (``[]`` clears it)."""

    participation_ids: list[int] = Field(max_length=CAMPAIGN_SESSION_MAX_ATTENDEES)


class SessionAttendee(BaseModel):
    """A character that attended the session, with its player."""

    participation_id: int
    character_id: int
    character_name: str
    owner: UserBrief


class CampaignSessionBrief(BaseModel):
    """A row of the session list (schedule and archive); the chronicle only comes with the single session."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    title: str
    status: CampaignSessionStatus
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    attendees: list[SessionAttendee] = Field(default_factory=list)


class CampaignSessionResponse(CampaignSessionBrief):
    """
    One session. ``chronicle_markdown`` is ``null`` for players until the GM publishes it, and comes without
    ``:::gm`` blocks afterwards.
    """

    chronicle_markdown: str | None
    created_at: datetime
    updated_at: datetime


class ScheduleCampaign(BaseModel):
    """The campaign a schedule entry belongs to."""

    id: int
    title: str


class ScheduleEntry(BaseModel):
    """``GET /campaigns/schedule``: one upcoming session of a campaign the caller runs or plays in."""

    id: int
    number: int
    title: str
    status: CampaignSessionStatus
    scheduled_at: datetime
    campaign: ScheduleCampaign
    viewer_role: ViewerRole
