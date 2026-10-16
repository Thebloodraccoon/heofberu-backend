"""Article links of a public campaign."""

from sqlalchemy import select

from app.features.public_campaigns.base import PublicCampaignScopedRepository
from app.models.articles.article_model import Article
from app.models.campaigns.public_campaign_model import PublicCampaign, PublicCampaignArticle


class PublicCampaignArticlesRepository(PublicCampaignScopedRepository):
    """Full replacement of the links."""

    async def existing_article_ids(self, article_ids: list[int]) -> set[int]:
        """Which of ``article_ids`` exist."""

        return set(await self.db.scalars(select(Article.id).where(Article.id.in_(article_ids))))

    async def replace_links(self, public_campaign_id: int, rows: list[dict]) -> None:
        """Delete the current links and insert ``rows`` (``article_id``/``position``/``note``); flush only."""

        await self.replace_child_rows(
            PublicCampaignArticle, PublicCampaign(id=public_campaign_id), "public_campaign_id", rows
        )
