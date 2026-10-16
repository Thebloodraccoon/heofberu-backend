"""Per-capability dependency providers for public campaigns (one ``PublicCampaign*Dep`` per service)."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.public_campaigns.articles.service import PublicCampaignArticlesService
from app.features.public_campaigns.crud.service import PublicCampaignCrudService
from app.features.public_campaigns.showcase.service import PublicCampaignShowcaseService


def get_public_campaign_crud_service(db: DatabaseDep) -> PublicCampaignCrudService:
    """Catalog, reads and the author's writes."""

    return PublicCampaignCrudService(db)


PublicCampaignCrudDep = Annotated[PublicCampaignCrudService, Depends(get_public_campaign_crud_service)]


def get_public_campaign_articles_service(db: DatabaseDep) -> PublicCampaignArticlesService:
    """Article links for GMs."""

    return PublicCampaignArticlesService(db)


PublicCampaignArticlesDep = Annotated[PublicCampaignArticlesService, Depends(get_public_campaign_articles_service)]


def get_public_campaign_showcase_service(db: DatabaseDep) -> PublicCampaignShowcaseService:
    """Characters and reviews aggregated from the linked game campaigns."""

    return PublicCampaignShowcaseService(db)


PublicCampaignShowcaseDep = Annotated[PublicCampaignShowcaseService, Depends(get_public_campaign_showcase_service)]
