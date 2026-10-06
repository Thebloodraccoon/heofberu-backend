"""Full replacement of a race's or subrace's ability bonuses, reconciling the characters built on them."""

from typing import Any

from app.constants import FeatureSourceType
from app.core.base.service import ServiceMixin
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.shared.catalog.schemas import AbilityBonusesUpdate


class AbilityBonusesManagerMixin(ServiceMixin):
    """
    Replace the owner's bonuses and reconcile the characters built on it.

    Bonus changes reach characters through ``feature_sync``, which also refreshes
    those characters' cached payloads. The mixin host is a ``BaseService``
    whose repository exposes ``set_ability_bonuses``.
    """

    _bonus_source_type: FeatureSourceType

    async def set_ability_bonuses(self, source_id: int, data: AbilityBonusesUpdate) -> Any:
        """Fully replace the bonuses of ``source_id`` and refresh affected characters' stats."""

        bonuses = [{"ability": item.ability, "bonus": item.bonus} for item in data.ability_bonuses]
        async with self._atomic():
            await self._exists_or_404(source_id)
            await self.repository.set_ability_bonuses(source_id, bonuses)
            await reconcile_characters_for_source(self.repository.db, self._bonus_source_type, source_id)
            await self._invalidate_cache()

        return await self._get_response(source_id)
