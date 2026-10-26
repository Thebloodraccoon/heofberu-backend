"""
Public campaigns (presets/announcements): GMs write them, everyone reads the published ones.

The author publishes their own (no review step); the founder moderates afterwards (archive). Players and guests see
only ``PUBLISHED`` presets, with ``:::gm`` blocks stripped; article links are only under ``/{id}/articles`` (GM).
"""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PublicCampaignStatus, UserRole
from app.core.exceptions import RecordIdsInvalidError
from app.core.pagination import Page, paginate
from app.features.public_campaigns.base import PublicCampaignScopedService, is_gm_reader
from app.features.public_campaigns.crud.repository import PublicCampaignCrudRepository
from app.features.public_campaigns.exceptions import (
    PublicCampaignNotFoundException,
    PublicCampaignStatusTransitionException,
)
from app.features.public_campaigns.schemas import (
    PublicCampaignCreate,
    PublicCampaignListItem,
    PublicCampaignResponse,
    PublicCampaignUpdate,
)
from app.features.shared.secrets import strip_gm_blocks
from app.features.users.schemas import UserResponse
from app.models.campaigns.public_campaign_model import PublicCampaign

PublicCampaignAction = Literal["publish", "unpublish", "archive"]

#: action -> (statuses it's allowed from, resulting status).
TRANSITIONS: dict[PublicCampaignAction, tuple[frozenset[PublicCampaignStatus], PublicCampaignStatus]] = {
    "publish": (
        frozenset({PublicCampaignStatus.DRAFT, PublicCampaignStatus.ARCHIVED}),
        PublicCampaignStatus.PUBLISHED,
    ),
    "unpublish": (frozenset({PublicCampaignStatus.PUBLISHED}), PublicCampaignStatus.DRAFT),
    "archive": (
        frozenset({PublicCampaignStatus.DRAFT, PublicCampaignStatus.PUBLISHED}),
        PublicCampaignStatus.ARCHIVED,
    ),
}


class PublicCampaignCrudService(PublicCampaignScopedService):
    """Catalog, reads, create/update and the publish/unpublish/archive moves."""

    repository: PublicCampaignCrudRepository

    def __init__(self, db: AsyncSession):
        """Initialize the CRUD repository."""

        super().__init__(PublicCampaignCrudRepository(db))

    async def list_catalog(
        self,
        user: UserResponse | None,
        *,
        statuses: tuple[PublicCampaignStatus, ...],
        query: str | None,
        tag_ids: tuple[int, ...],
        author_id: int | None,
        page: int,
        size: int,
    ) -> Page[PublicCampaignListItem]:
        """
        The catalog. ``statuses`` only matters for GMs, and unpublished presets are a GM's own (any for the
        founder); everyone else always gets published presets.
        """

        is_gm = is_gm_reader(user)
        if not is_gm or not statuses:
            statuses = (PublicCampaignStatus.PUBLISHED,)
        unpublished_of = user.id if is_gm and user.role != UserRole.FOUND_FATHER else None
        skip, limit = paginate(page, size)
        rows, total = await self.repository.list_catalog(
            statuses=statuses,
            query=query,
            tag_ids=tag_ids,
            author_id=author_id,
            unpublished_of=unpublished_of,
            skip=skip,
            limit=limit,
        )
        items = [self._list_item(row.PublicCampaign, row.campaign_count, is_gm=is_gm) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def get(self, public_campaign_id: int, user: UserResponse | None) -> PublicCampaignResponse:
        """One preset in the reader's view (404 for an unpublished one unless its author or the founder)."""

        await self._visible_state(public_campaign_id, user)
        return await self._response(public_campaign_id, user)

    async def get_by_slug(self, slug: str, user: UserResponse | None) -> PublicCampaignResponse:
        """``get`` by slug."""

        public_campaign_id = await self.repository.get_id_by_slug(slug)
        if public_campaign_id is None:
            raise PublicCampaignNotFoundException(slug)

        return await self.get(public_campaign_id, user)

    async def create(self, data: PublicCampaignCreate, user: UserResponse) -> PublicCampaignResponse:
        """Create a draft authored by the caller (a GM)."""

        tag_ids = await self._checked_tag_ids(data.tag_ids)
        async with self._atomic():
            slug = await self.repository.generate_unique_slug(data.title)
            public_campaign = await self.repository.create(
                {**data.model_dump(exclude={"tag_ids"}), "slug": slug, "author_id": user.id}
            )
            public_campaign_id = public_campaign.id
            if tag_ids:
                await self.repository.set_tags(public_campaign_id, tag_ids)

        return await self._response(public_campaign_id, user)

    async def update(
        self, public_campaign_id: int, data: PublicCampaignUpdate, user: UserResponse
    ) -> PublicCampaignResponse:
        """Partial update (author/founder). The slug stays: links shared in chats keep working after a rename."""

        await self._editable_state(public_campaign_id, user)
        fields = data.model_dump(exclude_unset=True)
        tag_ids = await self._checked_tag_ids(fields.pop("tag_ids")) if "tag_ids" in fields else None

        async with self._atomic():
            public_campaign = await self.repository.get_by_id(public_campaign_id)
            if tag_ids is not None:
                await self.repository.set_tags(public_campaign_id, tag_ids)
                # A tags-only PATCH writes no preset column, so ``onupdate`` wouldn't move ``updated_at``.
                fields.setdefault("updated_at", self.clock())
            if fields:
                await self.repository.update(public_campaign, fields)

        return await self._response(public_campaign_id, user)

    async def transition(
        self, public_campaign_id: int, action: PublicCampaignAction, user: UserResponse
    ) -> PublicCampaignResponse:
        """Apply ``action`` (author/founder); the first publish stamps ``published_at``."""

        state = await self._editable_state(public_campaign_id, user)
        allowed_from, target = TRANSITIONS[action]
        if state.status not in allowed_from:
            raise PublicCampaignStatusTransitionException(public_campaign_id, action, state.status.value)

        async with self._atomic():
            public_campaign = await self.repository.get_by_id(public_campaign_id)
            fields: dict = {"status": target}
            if target == PublicCampaignStatus.PUBLISHED and public_campaign.published_at is None:
                fields["published_at"] = self.clock()
            await self.repository.update(public_campaign, fields)

        return await self._response(public_campaign_id, user)

    async def _checked_tag_ids(self, tag_ids: list[int]) -> list[int]:
        """``tag_ids`` if all exist, else 400 listing the unknown ones."""

        missing = sorted(set(tag_ids) - await self.repository.existing_tag_ids(tag_ids))
        if missing:
            raise RecordIdsInvalidError("Tags", missing)

        return tag_ids

    async def _response(self, public_campaign_id: int, user: UserResponse | None) -> PublicCampaignResponse:
        """The full preset in the reader's view."""

        public_campaign = await self.repository.get_by_id(public_campaign_id)
        is_gm = is_gm_reader(user)
        item = self._list_item(public_campaign, await self.repository.campaign_count(public_campaign_id), is_gm=is_gm)
        description = public_campaign.description_markdown
        return PublicCampaignResponse(
            **item.model_dump(),
            description_markdown=(description if is_gm else strip_gm_blocks(description)) or "",
            created_at=public_campaign.created_at,
        )

    @staticmethod
    def _list_item(public_campaign: PublicCampaign, campaign_count: int, *, is_gm: bool) -> PublicCampaignListItem:
        """The catalog card; the pitch loses ``:::gm`` blocks for non-GMs, like the description."""

        author = public_campaign.author
        return PublicCampaignListItem(
            id=public_campaign.id,
            slug=public_campaign.slug,
            title=public_campaign.title,
            pitch=(public_campaign.pitch if is_gm else strip_gm_blocks(public_campaign.pitch)) or "",
            status=public_campaign.status,
            author={"id": author.id, "username": author.username} if author is not None else None,
            tags=[{"id": tag.id, "name": tag.name} for tag in public_campaign.tags],
            campaign_count=campaign_count or 0,
            published_at=public_campaign.published_at,
            updated_at=public_campaign.updated_at,
        )
