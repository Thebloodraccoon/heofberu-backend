"""The knowledge-base articles a public campaign points GMs to (lore, NPCs, locations, homerules)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordIdsInvalidError
from app.features.public_campaigns.articles.repository import PublicCampaignArticlesRepository
from app.features.public_campaigns.base import PublicCampaignScopedService
from app.features.public_campaigns.schemas import PublicCampaignArticleLink, PublicCampaignArticlesUpdate
from app.features.users.schemas import UserResponse


class PublicCampaignArticlesService(PublicCampaignScopedService):
    """
    Links are references, never copies: a game campaign made from the preset reads the same articles. Each article
    keeps its own visibility (a ``gm_only`` one stays GM-only); the link list itself is shown to GMs only.
    """

    repository: PublicCampaignArticlesRepository

    def __init__(self, db: AsyncSession):
        """Initialize the links repository."""

        super().__init__(PublicCampaignArticlesRepository(db))

    async def list_links(self, public_campaign_id: int, user: UserResponse) -> list[PublicCampaignArticleLink]:
        """The links in order (the router allows GMs only)."""

        await self._visible_state(public_campaign_id, user)
        rows = await self.repository.list_article_links(public_campaign_id)
        return [PublicCampaignArticleLink.model_validate(dict(row._mapping)) for row in rows]

    async def set_links(
        self, public_campaign_id: int, data: PublicCampaignArticlesUpdate, user: UserResponse
    ) -> list[PublicCampaignArticleLink]:
        """
        Replace all links. Any GM who sees the preset may (the router allows GMs only), not just its author: the
        knowledge base is shared work. Duplicates keep their first entry; unknown article ids are a 400.
        """

        await self._visible_state(public_campaign_id, user)
        entries, seen = [], set()
        for index, entry in enumerate(data.articles):
            if entry.article_id in seen:
                continue
            seen.add(entry.article_id)
            position = entry.position if entry.position is not None else index
            entries.append({"article_id": entry.article_id, "position": position, "note": entry.note})

        missing = sorted(seen - await self.repository.existing_article_ids(list(seen))) if seen else []
        if missing:
            raise RecordIdsInvalidError("Articles", missing)

        async with self._atomic():
            await self.repository.replace_links(public_campaign_id, entries)

        return await self.list_links(public_campaign_id, user)
