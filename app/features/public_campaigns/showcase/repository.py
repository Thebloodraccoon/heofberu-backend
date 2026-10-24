"""
Showcase queries: what the game campaigns made from a preset contribute to its public page.

Read-only edge into the characters domain (``characters.visibility.repository`` column helpers) so the showcase row
and the public character card can never drift apart. Nothing campaign-private is selected: no campaign title, no
chronicle, no notes.
"""

from typing import Any

from sqlalchemy import select

from app.constants import CampaignCharacterStatus, CharacterPublicVisibility
from app.core.pagination import fetch_page
from app.features.characters.visibility.repository import summary_columns, with_summary_joins
from app.features.public_campaigns.base import PublicCampaignScopedRepository
from app.models.campaigns.campaign_character_model import CampaignCharacter
from app.models.campaigns.campaign_model import Campaign
from app.models.campaigns.campaign_review_model import CampaignReview
from app.models.character.character_model import Character
from app.models.user_model import User


class PublicCampaignShowcaseRepository(PublicCampaignScopedRepository):
    """Characters and reviews aggregated over every game campaign linked to the preset."""

    async def list_characters(self, public_campaign_id: int, *, skip: int, limit: int) -> tuple[list[Any], int]:
        """
        Characters that played in a campaign made from the preset (participation not ``REMOVED``) and whose owners
        show them publicly, by name. A character that played there twice appears once.
        """

        played_here = (
            select(CampaignCharacter.character_id)
            .join(Campaign, Campaign.id == CampaignCharacter.campaign_id)
            .where(
                Campaign.public_campaign_id == public_campaign_id,
                CampaignCharacter.status != CampaignCharacterStatus.REMOVED,
            )
        )
        conditions = [
            Character.id.in_(played_here),
            Character.public_visibility != CharacterPublicVisibility.HIDDEN,
        ]
        stmt = with_summary_joins(select(*summary_columns()).select_from(Character))
        return await fetch_page(
            self.db, stmt.where(*conditions).order_by(Character.name, Character.id), skip=skip, limit=limit
        )

    async def list_reviews(self, public_campaign_id: int, *, skip: int, limit: int) -> tuple[list[Any], int]:
        """Visible campaign reviews of every linked game campaign, newest first."""

        conditions = [Campaign.public_campaign_id == public_campaign_id, CampaignReview.hidden_at.is_(None)]
        stmt = (
            select(
                CampaignReview.id,
                CampaignReview.body,
                CampaignReview.created_at,
                CampaignReview.edited_at,
                User.id.label("author_id"),
                User.username.label("author_username"),
            )
            .join(Campaign, Campaign.id == CampaignReview.campaign_id)
            .join(User, User.id == CampaignReview.author_id)
            .where(*conditions)
            .order_by(CampaignReview.created_at.desc(), CampaignReview.id.desc())
        )
        return await fetch_page(self.db, stmt, skip=skip, limit=limit)
