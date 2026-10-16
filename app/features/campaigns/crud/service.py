"""Campaign CRUD: create (from scratch or from a preset), read, "my campaigns", update, archive."""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CAMPAIGN_CLOSED_STATUSES, PublicCampaignStatus, UserRole
from app.core.pagination import Page, paginate
from app.features.campaigns.access import CampaignContext
from app.features.campaigns.base import CampaignScopedService
from app.features.campaigns.crud.repository import CampaignRepository
from app.features.campaigns.crud.schemas import (
    CampaignCreate,
    CampaignListItem,
    CampaignResponse,
    CampaignUpdate,
    MyCampaignCharacter,
)
from app.features.campaigns.exceptions import CampaignListFilterException, PublicCampaignLinkNotFoundException
from app.features.campaigns.schemas import PublicCampaignBrief, UserBrief
from app.features.public_campaigns.base import can_edit_preset
from app.features.shared.secrets import strip_gm_blocks
from app.features.users.schemas import UserResponse
from app.models.campaigns.campaign_model import Campaign


class CampaignCrudService(CampaignScopedService):
    """
    The campaign itself. Only GM-role users create campaigns; afterwards everything goes through the
    ``CampaignContext`` (owner/founder write, players read the stripped view). There is no DELETE: a campaign is
    archived (players keep reading it), so the session history and reviews written by others survive.
    """

    repository: CampaignRepository

    def __init__(self, db: AsyncSession):
        """Initialize the campaign repository."""

        super().__init__(CampaignRepository(db))

    async def create(self, data: CampaignCreate, current_user: UserResponse) -> CampaignResponse:
        """Create a campaign owned by the caller (a GM), copying omitted title/description from the preset."""

        fields = data.model_dump()
        if data.public_campaign_id is not None:
            preset = await self._preset_or_400(data.public_campaign_id, current_user)
            if fields["title"] is None:
                fields["title"] = preset.title
            if fields["description_markdown"] is None:
                fields["description_markdown"] = preset.description_markdown
        if fields["description_markdown"] is None:
            fields["description_markdown"] = ""

        async with self._atomic():
            campaign = await self.repository.create({**fields, "owner_id": current_user.id})
            campaign_id = campaign.id

        return await self.get(campaign_id, current_user)

    async def get(self, campaign_id: int, current_user: UserResponse) -> CampaignResponse:
        """One campaign in the caller's view (404 for outsiders)."""

        ctx = await self._reader(campaign_id, current_user)
        campaign = await self.repository.get_by_id(campaign_id)
        mine = await self.repository.my_characters(current_user.id, [campaign_id])
        return self._response(campaign, ctx, mine.get(campaign_id, []))

    async def list_mine(
        self,
        current_user: UserResponse,
        *,
        role: Literal["gm", "player"] | None,
        include_archived: bool,
        all_campaigns: bool,
        page: int,
        size: int,
        query: str | None = None,
    ) -> Page[CampaignListItem]:
        """
        Campaigns the caller runs (``role=gm``), plays in (``role=player``) or both (default). ``all_campaigns`` is
        the founder's view of every campaign (ignored for anyone else).

        Raises:
            CampaignListFilterException: the founder combined ``role`` with ``all_campaigns`` (400).
        """

        skip, limit = paginate(page, size)
        all_campaigns = all_campaigns and current_user.role == UserRole.FOUND_FATHER
        if all_campaigns and role is not None:
            raise CampaignListFilterException()
        rows, total = await self.repository.list_for_user(
            current_user.id,
            all_campaigns=all_campaigns,
            role=role,
            query=query,
            include_archived=include_archived,
            skip=skip,
            limit=limit,
        )
        mine = await self.repository.my_characters(current_user.id, [row.Campaign.id for row in rows])
        items = [
            self._list_item(
                row.Campaign,
                CampaignContext.of(current_user, row.Campaign.id, row.Campaign.owner_id, row.is_player),
                mine.get(row.Campaign.id, []),
            )
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def update(self, campaign_id: int, data: CampaignUpdate, current_user: UserResponse) -> CampaignResponse:
        """Partial update (GM). Closing the campaign (finished/abandoned) releases its active characters."""

        await self._gm(campaign_id, current_user)
        fields = data.model_dump(exclude_unset=True)
        if fields.get("public_campaign_id") is not None:
            await self._preset_or_400(fields["public_campaign_id"], current_user)

        async with self._atomic():
            await self.repository.lock_campaign(campaign_id)
            campaign = await self.repository.get_by_id(campaign_id)
            await self.repository.update(campaign, fields)
            if fields.get("status") in CAMPAIGN_CLOSED_STATUSES:
                await self.repository.release_characters(campaign_id, self.clock())

        return await self.get(campaign_id, current_user)

    async def archive(self, campaign_id: int, current_user: UserResponse) -> CampaignResponse:
        """Archive (GM): hidden from "my campaigns" by default, still readable, characters released."""

        await self._gm(campaign_id, current_user)
        async with self._atomic():
            await self.repository.lock_campaign(campaign_id)
            campaign = await self.repository.get_by_id(campaign_id)
            if campaign.archived_at is None:
                now = self.clock()
                await self.repository.update(campaign, {"archived_at": now})
                await self.repository.release_characters(campaign_id, now)

        return await self.get(campaign_id, current_user)

    async def restore(self, campaign_id: int, current_user: UserResponse) -> CampaignResponse:
        """Take the campaign out of the archive (GM). Released characters stay released: re-add them."""

        await self._gm(campaign_id, current_user)
        async with self._atomic():
            campaign = await self.repository.get_by_id(campaign_id)
            await self.repository.update(campaign, {"archived_at": None})

        return await self.get(campaign_id, current_user)

    async def _preset_or_400(self, public_campaign_id: int, current_user: UserResponse):
        """
        The preset to copy from / link to: a published one, or (for its author and the founder) a draft.

        400 rather than 404: the campaign is fine, the referenced preset is the problem.
        """

        preset = await self.repository.get_public_campaign(public_campaign_id, include_unpublished=True)
        if preset is None:
            raise PublicCampaignLinkNotFoundException(public_campaign_id)

        if preset.status != PublicCampaignStatus.PUBLISHED and not can_edit_preset(current_user, preset.author_id):
            raise PublicCampaignLinkNotFoundException(public_campaign_id)

        return preset

    @staticmethod
    def _list_item(campaign: Campaign, ctx: CampaignContext, my_characters: list | tuple = ()) -> CampaignListItem:
        """A listing row in the caller's view, with the caller's own characters at the table."""

        return CampaignListItem(
            id=campaign.id,
            title=campaign.title,
            status=campaign.status,
            owner=UserBrief.model_validate(campaign.owner) if campaign.owner is not None else None,
            public_campaign=PublicCampaignBrief.model_validate(campaign.public_campaign)
            if campaign.public_campaign is not None
            else None,
            viewer_role=ctx.role,
            updated_at=campaign.updated_at,
            archived_at=campaign.archived_at,
            my_characters=[
                MyCampaignCharacter(
                    participation_id=row.participation_id,
                    character_id=row.character_id,
                    name=row.name,
                    status=row.status,
                )
                for row in my_characters
            ],
        )

    @classmethod
    def _response(cls, campaign: Campaign, ctx: CampaignContext, my_characters: list | tuple = ()) -> CampaignResponse:
        """The full campaign; the description loses its ``:::gm`` blocks for players."""

        description = campaign.description_markdown if ctx.is_gm else strip_gm_blocks(campaign.description_markdown)
        return CampaignResponse(
            **cls._list_item(campaign, ctx, my_characters).model_dump(),
            description_markdown=description or "",
            created_at=campaign.created_at,
        )
