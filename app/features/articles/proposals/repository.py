"""Queries over ``article_proposals``."""

from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleProposalStatus
from app.models.articles.article_model import Article
from app.models.articles.article_proposal_model import ArticleProposal


def _with_article():
    """
    ``(proposal, article title, slug, version)`` rows: plain columns, so no partial ``Article`` lands in the
    session; the version tells whether a pending proposal is stale.
    """

    return select(ArticleProposal, Article.title, Article.slug, Article.version).join(
        Article, Article.id == ArticleProposal.article_id
    )


class ArticleProposalRepository:
    """Create, read and close proposals; every read is for GMs, so no visibility filtering."""

    def __init__(self, db: AsyncSession):
        """Bind to a session."""

        self.db = db

    async def create(self, data: dict) -> int:
        """Insert a proposal and return its id (flush only; the service commits through ``atomic``)."""

        proposal = ArticleProposal(**data)
        self.db.add(proposal)
        await self.db.flush()
        return proposal.id

    async def get(self, article_id: int, proposal_id: int) -> Any:
        """
        One ``(proposal, title, slug, version)`` row of that article, or ``None``. Always re-read from the database
        (``populate_existing``): ``close`` is a bulk UPDATE and the session doesn't expire on commit.
        """

        result = await self.db.execute(
            _with_article()
            .where(ArticleProposal.id == proposal_id, ArticleProposal.article_id == article_id)
            .execution_options(populate_existing=True)
        )
        return result.one_or_none()

    async def list_proposals(
        self,
        *,
        article_id: int | None = None,
        statuses: list[ArticleProposalStatus] | None = None,
        article_author_id: int | None = None,
        proposer_id: int | None = None,
        skip: int = 0,
        limit: int,
        before_id: int | None = None,
        with_total: bool = True,
    ) -> tuple[list[Any], int | None]:
        """
        ``(proposal, title, slug, version)`` rows, newest first, and the total (``None`` without ``with_total``).

        Filters: one article, any of ``statuses``, articles written by ``article_author_id``, ``proposer_id``;
        ``before_id`` is the keyset position (proposals older than that id).
        """

        conditions = []
        if article_id is not None:
            conditions.append(ArticleProposal.article_id == article_id)
        if statuses:
            conditions.append(ArticleProposal.status.in_(statuses))
        if article_author_id is not None:
            conditions.append(Article.author_id == article_author_id)
        if proposer_id is not None:
            conditions.append(ArticleProposal.proposer_id == proposer_id)

        total = None
        if with_total:
            total = await self.db.scalar(
                select(func.count())
                .select_from(ArticleProposal)
                .join(Article, Article.id == ArticleProposal.article_id)
                .where(*conditions)
            )
        if before_id is not None:
            conditions.append(ArticleProposal.id < before_id)

        result = await self.db.execute(
            _with_article().where(*conditions).order_by(ArticleProposal.id.desc()).offset(skip).limit(limit)
        )
        return list(result.all()), total

    async def lock(self, article_id: int, proposal_id: int) -> ArticleProposal | None:
        """Lock the proposal row until the transaction ends and return it, freshly read (``None`` if absent)."""

        return await self.db.scalar(
            select(ArticleProposal)
            .where(ArticleProposal.id == proposal_id, ArticleProposal.article_id == article_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def replace_content(self, proposal_id: int, content: dict, *, base_version: int) -> None:
        """Overwrite the proposed content and its ``base_version`` (no commit; call under ``lock``)."""

        await self.db.execute(
            update(ArticleProposal)
            .where(ArticleProposal.id == proposal_id)
            .values(**content, base_version=base_version)
            .execution_options(synchronize_session=False)
        )

    async def close(
        self,
        proposal_id: int,
        status: ArticleProposalStatus,
        *,
        reviewer_id: int | None,
        accepted_version: int | None = None,
        review_note: str | None = None,
    ) -> bool:
        """
        Move a PENDING proposal to ``status`` (one conditional UPDATE, no commit); ``False`` if it wasn't pending,
        so two reviewers (or a reviewer and the withdrawing proposer) can't both close it.
        """

        result = await self.db.execute(
            update(ArticleProposal)
            .where(ArticleProposal.id == proposal_id, ArticleProposal.status == ArticleProposalStatus.PENDING)
            .values(
                status=status,
                reviewer_id=reviewer_id,
                reviewed_at=func.now(),
                accepted_version=accepted_version,
                review_note=review_note,
            )
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1
