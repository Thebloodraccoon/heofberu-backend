"""Public campaign CRUD queries: catalog, slugs, tags and the linked-campaign count."""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import PublicCampaignStatus
from app.core.pagination import fetch_page
from app.features.public_campaigns.base import PublicCampaignScopedRepository
from app.features.shared.slug import slugify
from app.models.campaigns.campaign_model import Campaign
from app.models.campaigns.public_campaign_model import PublicCampaign, public_campaign_tags
from app.models.tag_model import Tag

SLUG_FALLBACK = "campaign"


def campaign_counts() -> Any:
    """
    ``(public_campaign_id, campaign_count)`` for every preset that has game campaigns, grouped once per query; the
    catalog LEFT JOINs it instead of running a correlated count per row (served by ``ix_campaigns_public_campaign_id``).
    """

    return (
        select(Campaign.public_campaign_id, func.count().label("campaign_count"))
        .where(Campaign.public_campaign_id.is_not(None))
        .group_by(Campaign.public_campaign_id)
        .subquery("campaign_counts")
    )


class PublicCampaignCrudRepository(PublicCampaignScopedRepository):
    """Presets with author and tags eager-loaded."""

    def __init__(self, db: AsyncSession):
        """Eager-load what every response shows: author and tags."""

        super().__init__(
            db, default_load_options=[selectinload(PublicCampaign.author), selectinload(PublicCampaign.tags)]
        )

    async def list_catalog(
        self,
        *,
        statuses: tuple[PublicCampaignStatus, ...],
        query: str | None,
        tag_ids: tuple[int, ...],
        author_id: int | None,
        unpublished_of: int | None,
        skip: int,
        limit: int,
    ) -> tuple[list[Any], int]:
        """
        One page of ``(PublicCampaign, campaign_count)`` rows, newest published first, and the total.
        ``unpublished_of``: a GM sees drafts/archived presets of their own only (``None``: no such limit).
        """

        conditions: list[Any] = [PublicCampaign.status.in_(statuses)]
        if unpublished_of is not None:
            conditions.append(
                or_(PublicCampaign.status == PublicCampaignStatus.PUBLISHED, PublicCampaign.author_id == unpublished_of)
            )
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(
                or_(
                    PublicCampaign.title.ilike(f"%{escaped}%", escape="\\"),
                    PublicCampaign.pitch.ilike(f"%{escaped}%", escape="\\"),
                )
            )
        if tag_ids:
            conditions.append(
                PublicCampaign.id.in_(
                    select(public_campaign_tags.c.public_campaign_id).where(public_campaign_tags.c.tag_id.in_(tag_ids))
                )
            )
        if author_id is not None:
            conditions.append(PublicCampaign.author_id == author_id)

        counts = campaign_counts()
        stmt = (
            select(PublicCampaign, func.coalesce(counts.c.campaign_count, 0).label("campaign_count"))
            .outerjoin(counts, counts.c.public_campaign_id == PublicCampaign.id)
            .options(*self._default_load_options)
            .where(*conditions)
            .order_by(
                func.coalesce(PublicCampaign.published_at, PublicCampaign.created_at).desc(), PublicCampaign.id.desc()
            )
        )
        return await fetch_page(self.db, stmt, skip=skip, limit=limit)

    async def campaign_count(self, public_campaign_id: int) -> int:
        """How many game campaigns link to the preset."""

        return (
            await self.db.scalar(
                select(func.count()).select_from(Campaign).where(Campaign.public_campaign_id == public_campaign_id)
            )
        ) or 0

    async def generate_unique_slug(self, title: str) -> str:
        """``base``, then ``base-2``, ``base-3``, ... (a concurrent duplicate is a 409 from the unique index)."""

        base = slugify(title, fallback=SLUG_FALLBACK)
        stmt = select(PublicCampaign.slug).where(
            or_(PublicCampaign.slug == base, PublicCampaign.slug.like(f"{base}-%"))
        )
        taken = set((await self.db.execute(stmt)).scalars().all())

        candidate, suffix = base, 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"
            suffix += 1

        return candidate

    async def existing_tag_ids(self, tag_ids: list[int]) -> set[int]:
        """Which of ``tag_ids`` exist."""

        return {tag.id for tag in await self.get_many_by_ids(Tag, tag_ids)}

    async def set_tags(self, public_campaign_id: int, tag_ids: list[int]) -> None:
        """Replace the preset's tags (flush only)."""

        await self.replace_association(
            public_campaign_tags,
            PublicCampaign(id=public_campaign_id),
            "public_campaign_id",
            "tag_id",
            list(dict.fromkeys(tag_ids)),
        )
