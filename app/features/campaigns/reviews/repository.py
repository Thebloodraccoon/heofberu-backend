"""Review queries; who may read which review is filtered in SQL."""

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.base.repository import SessionRepository
from app.core.pagination import fetch_page
from app.features.campaigns.base import CampaignAccessMixin
from app.models.campaigns.campaign_review_model import CampaignReview, SessionReview
from app.models.campaigns.campaign_session_model import CampaignSession


class CampaignReviewsRepository(CampaignAccessMixin, SessionRepository):
    """Campaign reviews and session reviews of one campaign."""

    async def get_campaign_review(self, campaign_id: int, author_id: int) -> CampaignReview | None:
        """The author's review of the campaign."""

        return await self.db.scalar(
            select(CampaignReview)
            .where(CampaignReview.campaign_id == campaign_id, CampaignReview.author_id == author_id)
            .execution_options(populate_existing=True)
        )

    async def upsert_campaign_review(
        self, campaign_id: int, author_id: int, body: str, now: datetime
    ) -> int | None:
        """
        Create the author's review or replace its body in one ``INSERT ... ON CONFLICT DO UPDATE`` (flush only), so
        two concurrent first writes can't collide. A founder-hidden review is left untouched: ``None`` then.
        """

        insert = pg_insert(CampaignReview).values(campaign_id=campaign_id, author_id=author_id, body=body)
        statement = insert.on_conflict_do_update(
            constraint="uq_campaign_reviews_author",
            set_={"body": insert.excluded.body, "edited_at": now},
            where=CampaignReview.hidden_at.is_(None),
        ).returning(CampaignReview.id)

        review_id = (await self.db.execute(statement)).scalar_one_or_none()
        await self.flush()
        return review_id

    async def upsert_session_review(
        self, session_id: int, author_id: int, body: str, visible_to_table: bool, now: datetime
    ) -> int | None:
        """
        Create the author's session review or replace it in one ``INSERT ... ON CONFLICT DO UPDATE`` (flush only).
        A founder-hidden review is left untouched: ``None`` then.
        """

        insert = pg_insert(SessionReview).values(
            session_id=session_id, author_id=author_id, body=body, visible_to_table=visible_to_table
        )
        statement = insert.on_conflict_do_update(
            constraint="uq_session_reviews_author",
            set_={
                "body": insert.excluded.body,
                "visible_to_table": insert.excluded.visible_to_table,
                "edited_at": now,
            },
            where=SessionReview.hidden_at.is_(None),
        ).returning(SessionReview.id)

        review_id = (await self.db.execute(statement)).scalar_one_or_none()
        await self.flush()
        return review_id

    async def get_campaign_review_by_id(self, review_id: int) -> CampaignReview | None:
        """A campaign review by id (moderation)."""

        return await self.db.scalar(
            select(CampaignReview).where(CampaignReview.id == review_id).execution_options(populate_existing=True)
        )

    async def list_campaign_reviews(
        self, campaign_id: int, *, include_hidden: bool, skip: int, limit: int
    ) -> tuple[list[CampaignReview], int]:
        """One page of the campaign's reviews, oldest first; hidden ones only with ``include_hidden`` (founder)."""

        stmt = select(CampaignReview).where(CampaignReview.campaign_id == campaign_id)
        if not include_hidden:
            stmt = stmt.where(CampaignReview.hidden_at.is_(None))

        rows, total = await fetch_page(
            self.db, stmt.order_by(CampaignReview.created_at, CampaignReview.id), skip=skip, limit=limit
        )
        return [row.CampaignReview for row in rows], total

    async def session_state(self, campaign_id: int, session_id: int) -> Any:
        """``(published_at,)`` of the session if it belongs to the campaign, else ``None``."""

        result = await self.db.execute(
            select(CampaignSession.published_at).where(
                CampaignSession.id == session_id, CampaignSession.campaign_id == campaign_id
            )
        )
        return result.first()

    async def get_session_review(self, session_id: int, author_id: int) -> SessionReview | None:
        """The author's review of the session."""

        return await self.db.scalar(
            select(SessionReview)
            .where(SessionReview.session_id == session_id, SessionReview.author_id == author_id)
            .execution_options(populate_existing=True)
        )

    async def get_session_review_by_id(self, review_id: int) -> SessionReview | None:
        """A session review by id (moderation)."""

        return await self.db.scalar(
            select(SessionReview).where(SessionReview.id == review_id).execution_options(populate_existing=True)
        )

    async def list_session_reviews(
        self, session_id: int, *, viewer_id: int | None, include_hidden: bool, skip: int, limit: int
    ) -> tuple[list[SessionReview], int]:
        """
        One page of the session's reviews, oldest first. ``viewer_id=None``: all of them (the GM); otherwise the
        viewer's own plus the ones their authors opened to the table. Hidden ones only with ``include_hidden``
        (founder).
        """

        stmt = select(SessionReview).where(SessionReview.session_id == session_id)
        if not include_hidden:
            stmt = stmt.where(SessionReview.hidden_at.is_(None))
        if viewer_id is not None:
            stmt = stmt.where(or_(SessionReview.author_id == viewer_id, SessionReview.visible_to_table.is_(True)))

        rows, total = await fetch_page(
            self.db, stmt.order_by(SessionReview.created_at, SessionReview.id), skip=skip, limit=limit
        )
        return [row.SessionReview for row in rows], total
