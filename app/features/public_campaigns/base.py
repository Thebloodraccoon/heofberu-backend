"""Shared base of the public campaign capabilities: lookups, visibility and edit rights."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PublicCampaignStatus, UserRole
from app.core.base.repository import BaseRepository
from app.core.base.transaction import TransactionMixin
from app.features.public_campaigns.exceptions import (
    PublicCampaignEditForbiddenException,
    PublicCampaignNotFoundException,
)
from app.features.users.schemas import UserResponse
from app.models.articles.article_model import Article
from app.models.campaigns.public_campaign_model import PublicCampaign, PublicCampaignArticle
from app.settings._common import aware_utcnow


def is_gm_reader(user: UserResponse | None) -> bool:
    """GMs and the founder read the GM view of a preset they can see: ``:::gm`` blocks and the article links."""

    return user is not None and user.role in (UserRole.GM, UserRole.FOUND_FATHER)


def can_edit_preset(user: UserResponse, author_id: int | None) -> bool:
    """The preset's author or the founder: edits it, and may start a game campaign from it while it's a draft."""

    return user.role == UserRole.FOUND_FATHER or author_id == user.id


def can_see_preset(user: UserResponse | None, status: PublicCampaignStatus, author_id: int | None) -> bool:
    """A published preset is for everyone; a draft or an archived one only for its author and the founder."""

    return status == PublicCampaignStatus.PUBLISHED or (user is not None and can_edit_preset(user, author_id))


class PublicCampaignScopedRepository(BaseRepository[PublicCampaign]):
    """Plain ``PublicCampaign`` repository every capability builds on."""

    def __init__(self, db: AsyncSession, *, default_load_options: list[Any] | None = None):
        """Bind to ``PublicCampaign`` (not searchable by the generic search)."""

        super().__init__(PublicCampaign, db, default_load_options=default_load_options, search_fields=[])

    async def get_state(self, public_campaign_id: int) -> Any:
        """``(id, author_id, status)`` of the preset, or ``None``."""

        result = await self.db.execute(
            select(PublicCampaign.id, PublicCampaign.author_id, PublicCampaign.status).where(
                PublicCampaign.id == public_campaign_id
            )
        )
        return result.first()

    async def get_id_by_slug(self, slug: str) -> int | None:
        """The preset id for a slug."""

        return await self.db.scalar(select(PublicCampaign.id).where(PublicCampaign.slug == slug))

    async def list_article_links(self, public_campaign_id: int) -> list[Any]:
        """The preset's article links in order, with the article's slug/title/type."""

        result = await self.db.execute(
            select(
                PublicCampaignArticle.article_id,
                Article.slug,
                Article.title,
                Article.article_type,
                PublicCampaignArticle.position,
                PublicCampaignArticle.note,
            )
            .join(Article, Article.id == PublicCampaignArticle.article_id)
            .where(PublicCampaignArticle.public_campaign_id == public_campaign_id)
            .order_by(PublicCampaignArticle.position, PublicCampaignArticle.id)
        )
        return list(result.all())


class PublicCampaignScopedService(TransactionMixin):
    """Visibility and edit-right checks shared by the capability services."""

    repository: PublicCampaignScopedRepository
    #: Source of "now" for ``published_at`` / ``updated_at`` writes; tests pin it per instance.
    clock: Callable[[], datetime] = staticmethod(aware_utcnow)

    def __init__(self, repository: PublicCampaignScopedRepository):
        """Keep the capability repository."""

        self.repository = repository

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def _visible_state(self, public_campaign_id: int, user: UserResponse | None) -> Any:
        """The preset's state if the reader may see it (``can_see_preset``), else 404."""

        state = await self.repository.get_state(public_campaign_id)
        if state is None or not can_see_preset(user, state.status, state.author_id):
            raise PublicCampaignNotFoundException(public_campaign_id)

        return state

    async def _editable_state(self, public_campaign_id: int, user: UserResponse) -> Any:
        """The preset's state if ``user`` is its author or the founder (403), 404 when it doesn't exist."""

        state = await self.repository.get_state(public_campaign_id)
        if state is None:
            raise PublicCampaignNotFoundException(public_campaign_id)
        if not can_edit_preset(user, state.author_id):
            raise PublicCampaignEditForbiddenException(public_campaign_id)

        return state
