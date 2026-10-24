"""The public page's showcase: archetypes that played the preset, and the players' reviews of their campaigns."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, paginate
from app.features.characters.visibility.schemas import PublicCharacterSummary
from app.features.public_campaigns.base import PublicCampaignScopedService
from app.features.public_campaigns.schemas import PublicCampaignReview
from app.features.public_campaigns.showcase.repository import PublicCampaignShowcaseRepository
from app.features.users.schemas import UserResponse


class PublicCampaignShowcaseService(PublicCampaignScopedService):
    """
    Aggregated over every game campaign linked to the preset. Characters appear only while their owners show them
    (``public_visibility``), so switching it off removes them at once; reviews hidden by the founder never appear.
    """

    repository: PublicCampaignShowcaseRepository

    def __init__(self, db: AsyncSession):
        """Initialize the showcase repository."""

        super().__init__(PublicCampaignShowcaseRepository(db))

    async def list_characters(
        self, public_campaign_id: int, user: UserResponse | None, *, page: int, size: int
    ) -> Page[PublicCharacterSummary]:
        """Summary rows of the characters that played it (full cards: ``GET /characters/{id}/public``)."""

        await self._visible_state(public_campaign_id, user)
        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_characters(public_campaign_id, skip=skip, limit=limit)
        items = [
            PublicCharacterSummary.model_validate({key: value for key, value in row._mapping.items() if key != "total"})
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def list_reviews(
        self, public_campaign_id: int, user: UserResponse | None, *, page: int, size: int
    ) -> Page[PublicCampaignReview]:
        """The players' reviews of the game campaigns made from it, newest first."""

        await self._visible_state(public_campaign_id, user)
        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_reviews(public_campaign_id, skip=skip, limit=limit)
        items = [
            PublicCampaignReview(
                id=row.id,
                author={"id": row.author_id, "username": row.author_username},
                body=row.body,
                created_at=row.created_at,
                edited_at=row.edited_at,
            )
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)
