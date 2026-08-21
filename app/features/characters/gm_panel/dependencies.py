"""Per-capability dependency providers for the character GM panel."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.characters.gm_panel.asi.service import GmPanelAsiService
from app.features.characters.gm_panel.feats.service import GmPanelFeatService
from app.features.characters.gm_panel.features.service import GmPanelFeatureService
from app.features.characters.gm_panel.hp.service import GmPanelHpService
from app.features.characters.gm_panel.items.service import GmPanelItemService
from app.features.characters.gm_panel.stats.service import GmPanelStatsService


def get_gm_panel_feat_service(db: DatabaseDep) -> GmPanelFeatService:
    """Get the GM feat-grant service instance."""

    return GmPanelFeatService(db)


GmPanelFeatsDep = Annotated[GmPanelFeatService, Depends(get_gm_panel_feat_service)]


def get_gm_panel_feature_service(db: DatabaseDep) -> GmPanelFeatureService:
    """Get the GM feature-grant service instance."""

    return GmPanelFeatureService(db)


GmPanelFeaturesDep = Annotated[GmPanelFeatureService, Depends(get_gm_panel_feature_service)]


def get_gm_panel_item_service(db: DatabaseDep) -> GmPanelItemService:
    """Get the GM-panel item (inventory) service instance."""

    return GmPanelItemService(db)


GmPanelItemsDep = Annotated[GmPanelItemService, Depends(get_gm_panel_item_service)]


def get_gm_panel_asi_service(db: DatabaseDep) -> GmPanelAsiService:
    """Get the GM free-form ASI adjustment service instance."""

    return GmPanelAsiService(db)


GmPanelAsiDep = Annotated[GmPanelAsiService, Depends(get_gm_panel_asi_service)]


def get_gm_panel_hp_service(db: DatabaseDep) -> GmPanelHpService:
    """Get the GM max-HP service instance."""

    return GmPanelHpService(db)


GmPanelHpDep = Annotated[GmPanelHpService, Depends(get_gm_panel_hp_service)]


def get_gm_panel_stats_service(db: DatabaseDep) -> GmPanelStatsService:
    """Get the GM stats-overview service instance."""

    return GmPanelStatsService(db)


GmPanelStatsDep = Annotated[GmPanelStatsService, Depends(get_gm_panel_stats_service)]
