"""Article review workflow: draft → in_review → published, plus reject, archive and restore."""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleStatus
from app.core.exceptions import RecordNotFoundError
from app.features.articles.access import ArticleActor
from app.features.articles.base import ArticleScopedService
from app.features.articles.cache import invalidate_article_trees, invalidate_articles
from app.features.articles.crud.schemas import ArticleResponse
from app.features.articles.exceptions import ArticleStatusTransitionException, ArticleVersionMismatchException
from app.features.articles.workflow.repository import ArticleWorkflowRepository

ArticleAction = Literal["submit", "publish", "reject", "archive", "restore"]

#: Review workflow: action -> (statuses it's allowed from, resulting status). New articles start as DRAFT.
ARTICLE_TRANSITIONS: dict[ArticleAction, tuple[frozenset[ArticleStatus], ArticleStatus]] = {
    "submit": (frozenset({ArticleStatus.DRAFT}), ArticleStatus.IN_REVIEW),
    "publish": (frozenset({ArticleStatus.IN_REVIEW}), ArticleStatus.PUBLISHED),
    "reject": (frozenset({ArticleStatus.IN_REVIEW}), ArticleStatus.DRAFT),
    "archive": (
        frozenset({ArticleStatus.DRAFT, ArticleStatus.IN_REVIEW, ArticleStatus.PUBLISHED}),
        ArticleStatus.ARCHIVED,
    ),
    "restore": (frozenset({ArticleStatus.ARCHIVED}), ArticleStatus.DRAFT),
}

#: Actions that record the actor as ``reviewed_by_id``.
REVIEW_ACTIONS = frozenset({"publish", "reject"})


class ArticleWorkflowService(ArticleScopedService):
    """
    The only place ``articles.status`` changes (an edit never moves it, so a published article stays published).

    Who may act is checked by the router (``submit``: any GM, then author/founder here; the rest: founder only).
    """

    repository: ArticleWorkflowRepository

    def __init__(self, db: AsyncSession):
        """Initialize the workflow repository."""

        super().__init__(ArticleWorkflowRepository(db))

    async def transition(
        self, article_id: int, action: ArticleAction, *, actor: ArticleActor, expected_version: int | None = None
    ) -> ArticleResponse:
        """
        Apply a review ``action`` (see ``ARTICLE_TRANSITIONS``) and return the article.

        The status check and the write are one conditional UPDATE, so concurrent actions can't both pass a stale
        check. ``actor`` is recorded as ``reviewed_by_id`` for ``publish``/``reject``; the first publish stamps
        ``published_at``. ``publish`` takes the ``expected_version`` the founder reviewed, so what gets published
        is exactly what was read.

        Raises:
            RecordNotFoundError: no such article.
            ArticleEditForbiddenException: ``submit`` by a GM who is neither the author nor the founder (403).
            ArticleVersionMismatchException: the article was edited after ``expected_version`` (409).
            ArticleStatusTransitionException: the current status doesn't allow ``action`` (409).
        """

        allowed_from, target = ARTICLE_TRANSITIONS[action]

        if action == "submit":
            actor.ensure_can_edit(article_id, (await self._write_state_or_404(article_id)).author_id)

        async with self._atomic():
            moved = await self.repository.transition_status(
                article_id,
                allowed_from,
                target,
                reviewer_id=actor.id if action in REVIEW_ACTIONS else None,
                expected_version=expected_version,
            )
            if moved:
                await invalidate_articles(self.repository.db, article_id)
                await invalidate_article_trees(self.repository.db)

        if not moved:
            state = await self._write_state_or_404(article_id)
            if ArticleStatus(state.status) in allowed_from and expected_version is not None:
                raise ArticleVersionMismatchException(article_id, expected_version, state.version)
            raise ArticleStatusTransitionException(article_id, action, ArticleStatus(state.status).value)

        return await self._get_response(article_id)

    async def _write_state_or_404(self, article_id: int):
        """The article's ``get_write_state`` row, or ``RecordNotFoundError``."""

        state = await self.repository.get_write_state(article_id)
        if state is None:
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        return state
