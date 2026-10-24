"""
Player reviews.

* Campaign review: one per player, public (inside the campaign and on its linked public campaign). The GM can't
  remove it; the founder can hide it.
* Session review: one per player and session, written once the chronicle is published. The GM always reads it;
  the rest of the table only when its author turns ``visible_to_table`` on. The founder can hide it too.

Only players write reviews (a character in the campaign that isn't ``REMOVED``); the campaign's own GM never does,
even with a character in the table. Writes are single upserts, so a double-submitted first review can't 409.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, paginate
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.exceptions import (
    CampaignReviewHiddenException,
    CampaignReviewNotFoundException,
    CampaignSessionNotFoundException,
    CampaignSessionNotPublishedException,
)
from app.features.campaigns.reviews.repository import CampaignReviewsRepository
from app.features.campaigns.reviews.schemas import (
    CampaignReviewResponse,
    CampaignReviewWrite,
    SessionReviewResponse,
    SessionReviewWrite,
)
from app.features.users.schemas import UserResponse


class CampaignReviewsService(CampaignScopedService):
    """Campaign and session reviews, plus the founder's hide/unhide."""

    repository: CampaignReviewsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the reviews repository."""

        super().__init__(CampaignReviewsRepository(db))

    # --- campaign reviews -------------------------------------------------------------------------------------

    async def list_campaign_reviews(
        self, campaign_id: int, current_user: UserResponse, *, page: int, size: int
    ) -> Page[CampaignReviewResponse]:
        """Every visible review of the campaign, oldest first (the founder also sees hidden ones)."""

        ctx = await self._reader(campaign_id, current_user)
        skip, limit = paginate(page, size)
        reviews, total = await self.repository.list_campaign_reviews(
            campaign_id, include_hidden=ctx.is_founder, skip=skip, limit=limit
        )
        items = [CampaignReviewResponse.model_validate(review) for review in reviews]
        return Page(items=items, total=total, page=page, size=size)

    async def put_campaign_review(
        self, campaign_id: int, data: CampaignReviewWrite, current_user: UserResponse
    ) -> CampaignReviewResponse:
        """
        Create or replace the caller's review of the campaign (players other than the campaign's GM).

        Raises:
            CampaignReviewHiddenException: the founder hid this review; it can be deleted, not edited (409).
        """

        async with self._atomic():
            await self._reviewer(campaign_id, current_user, lock=True)
            written = await self.repository.upsert_campaign_review(
                campaign_id, current_user.id, data.body, self.clock()
            )
            if written is None:
                raise CampaignReviewHiddenException(campaign_id)

        review = await self.repository.get_campaign_review(campaign_id, current_user.id)
        return CampaignReviewResponse.model_validate(review)

    async def delete_campaign_review(self, campaign_id: int, current_user: UserResponse) -> None:
        """Delete the caller's own review of the campaign (404 if there is none)."""

        async with self._atomic():
            await self._reader(campaign_id, current_user, lock=True)
            review = await self.repository.get_campaign_review(campaign_id, current_user.id)
            if review is None:
                raise CampaignReviewNotFoundException()
            await self.repository.db.delete(review)
            await self.repository.flush()

    async def set_campaign_review_hidden(self, review_id: int, hidden: bool) -> CampaignReviewResponse:
        """Hide or unhide a campaign review (the router guards this with ``FounderDep``)."""

        await self._set_hidden(self.repository.get_campaign_review_by_id, review_id, hidden)
        return CampaignReviewResponse.model_validate(await self.repository.get_campaign_review_by_id(review_id))

    # --- session reviews --------------------------------------------------------------------------------------

    async def list_session_reviews(
        self, campaign_id: int, session_id: int, current_user: UserResponse, *, page: int, size: int
    ) -> Page[SessionReviewResponse]:
        """The GM gets every review of the session; a player their own and those opened to the table."""

        ctx = await self._reader(campaign_id, current_user)
        await self._ensure_session(campaign_id, session_id)
        skip, limit = paginate(page, size)
        reviews, total = await self.repository.list_session_reviews(
            session_id,
            viewer_id=None if ctx.is_gm else current_user.id,
            include_hidden=ctx.is_founder,
            skip=skip,
            limit=limit,
        )
        items = [SessionReviewResponse.model_validate(review) for review in reviews]
        return Page(items=items, total=total, page=page, size=size)

    async def put_session_review(
        self, campaign_id: int, session_id: int, data: SessionReviewWrite, current_user: UserResponse
    ) -> SessionReviewResponse:
        """
        Create or replace the caller's review of a session (players only), once its chronicle is published.

        Raises:
            CampaignSessionNotPublishedException: the chronicle isn't published yet (409).
            CampaignReviewHiddenException: the founder hid this review; it can be deleted, not edited (409).
        """

        async with self._atomic():
            await self._reviewer(campaign_id, current_user, lock=True)
            await self._ensure_session(campaign_id, session_id, require_published=True)
            written = await self.repository.upsert_session_review(
                session_id, current_user.id, data.body, data.visible_to_table, self.clock()
            )
            if written is None:
                raise CampaignReviewHiddenException(campaign_id)

        review = await self.repository.get_session_review(session_id, current_user.id)
        return SessionReviewResponse.model_validate(review)

    async def delete_session_review(self, campaign_id: int, session_id: int, current_user: UserResponse) -> None:
        """Delete the caller's own review of the session."""

        async with self._atomic():
            await self._reader(campaign_id, current_user, lock=True)
            await self._ensure_session(campaign_id, session_id)
            review = await self.repository.get_session_review(session_id, current_user.id)
            if review is None:
                raise CampaignReviewNotFoundException()
            await self.repository.db.delete(review)
            await self.repository.flush()

    async def set_session_review_hidden(self, review_id: int, hidden: bool) -> SessionReviewResponse:
        """Hide or unhide a session review (the router guards this with ``FounderDep``)."""

        await self._set_hidden(self.repository.get_session_review_by_id, review_id, hidden)
        return SessionReviewResponse.model_validate(await self.repository.get_session_review_by_id(review_id))

    async def _set_hidden(self, get_review, review_id: int, hidden: bool) -> None:
        """Set or clear ``hidden_at`` on the review ``get_review(review_id)`` loads (404 if there is none)."""

        async with self._atomic():
            review = await get_review(review_id)
            if review is None:
                raise CampaignReviewNotFoundException(review_id)
            review.hidden_at = self.clock() if hidden else None
            await self.repository.flush()

    async def _ensure_session(self, campaign_id: int, session_id: int, *, require_published: bool = False) -> None:
        """404 for a session of another campaign; 409 for an unpublished chronicle when ``require_published``."""

        state = await self.repository.session_state(campaign_id, session_id)
        if state is None:
            raise CampaignSessionNotFoundException(campaign_id, session_id)
        if require_published and state.published_at is None:
            raise CampaignSessionNotPublishedException(session_id)
