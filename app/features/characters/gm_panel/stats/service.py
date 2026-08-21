"""GM stats-overview service: original base vs freshly computed effective scores."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore
from app.features.characters.ability_score.calculator import BASE_FIELD_BY_ABILITY, TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.gm_panel.stats.schemas import AbilityScoreView, GmCharacterStatsResponse
from app.features.users.schemas import UserResponse


class GmPanelStatsService(CharacterSubDomainService):
    """
    Per-ability ``{base, total}`` overview for the GM panel.

    Split out of the former ``CharacterGmPanelService`` — this capability
    owns the read-only ``GET /gm-panel/stats`` endpoint. Totals are
    freshly calculated from the current bonus sources (race/subrace
    bonuses + feat ASI choices), never read from the possibly-stale
    cache.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.stats_service = CharacterStatsService(db)

    async def get_stats(self, character_id: int, current_user: UserResponse) -> GmCharacterStatsResponse:
        """
        Return each ability's ORIGINAL base value next to its COMPUTED
        effective total.
        """

        character = await self.get_character_for_user(character_id, current_user)
        totals = await self.stats_service.compute(character)

        return GmCharacterStatsResponse(
            **{
                BASE_FIELD_BY_ABILITY[ability]: AbilityScoreView(
                    base=getattr(character, BASE_FIELD_BY_ABILITY[ability]),
                    total=totals[TOTAL_FIELD_BY_ABILITY[ability]],
                )
                for ability in AbilityScore
            }
        )
