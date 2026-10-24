"""Schemas of a campaign's roster and the character candidate search."""

from datetime import datetime

from pydantic import BaseModel

from app.constants import CampaignCharacterStatus
from app.features.campaigns.schemas import UserBrief


class CampaignCharacterAdd(BaseModel):
    """``POST /campaigns/{id}/characters``: a free character (not active in any campaign)."""

    character_id: int


class CampaignCharacterStatusUpdate(BaseModel):
    """``PATCH /campaigns/{id}/characters/{participation_id}``. ``active`` can't be set: re-add instead."""

    status: CampaignCharacterStatus


class CharacterBrief(BaseModel):
    """A character as the roster and the candidate search show it: never the sheet, never the backstory."""

    id: int
    name: str
    level: int
    class_name: str
    race_name: str | None = None


class CharacterCandidate(CharacterBrief):
    """A free character the GM may add, with its owner (the player)."""

    owner: UserBrief


class CampaignCharacterResponse(BaseModel):
    """One participation in the roster (a history row: the same character may appear again after ``removed``)."""

    id: int
    character: CharacterBrief
    owner: UserBrief
    status: CampaignCharacterStatus
    joined_at: datetime
    ended_at: datetime | None = None
