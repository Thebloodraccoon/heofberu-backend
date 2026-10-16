"""Schemas of the GM's private campaign notes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.features.campaigns.schemas import CampaignText, CampaignTitle


class CampaignNoteCreate(BaseModel):
    """``POST /campaigns/{id}/notes``."""

    title: CampaignTitle
    body_markdown: CampaignText = ""


class CampaignNoteUpdate(BaseModel):
    """``PATCH``: only sent fields change, none may be ``null``."""

    title: CampaignTitle | None = None
    body_markdown: CampaignText | None = None

    @model_validator(mode="after")
    def _no_null_fields(self) -> "CampaignNoteUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class CampaignNoteResponse(BaseModel):
    """A note."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body_markdown: str
    created_at: datetime
    updated_at: datetime
