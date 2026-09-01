"""GM max-HP service: the only write path for ``Character.max_hp``."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.hp.schemas import MaxHpUpdate
from app.features.characters.schemas import AbilityScoresResponse, CharacterResponse
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


class GmPanelHpService(CharacterSubDomainService):
    """Set a character's maximum HP directly (GM-only — the only write path for ``max_hp``); ``current_hp`` is clamped down when it exceeds the new maximum."""

    # Full CharacterResponse needs the eagerly loaded collections, not the light fetch.
    _light_character_fetch = False

    def __init__(self, db: AsyncSession):
        """Wire up the stats service."""

        super().__init__(db)
        self.stats_service = CharacterStatsService(db)

    async def set_max_hp(self, character_id: int, data: MaxHpUpdate, current_user: UserResponse) -> CharacterResponse:
        """Set a character's ``max_hp``, clamping ``current_hp`` down when it exceeds the new maximum."""

        character = await self.get_character_for_user(character_id, current_user)

        fields: dict[str, int] = {"max_hp": data.max_hp}
        if character.current_hp > data.max_hp:
            fields["current_hp"] = data.max_hp

        await self.repository.update(character, fields)
        await invalidate_character_cache(character_id)

        return await self._character_response(character)

    async def _character_response(self, character: Character) -> CharacterResponse:
        """Serialize a full ``CharacterResponse`` (cache row as-is + derived hit dice/speed)."""

        cache_row = await self.stats_service.get_or_stale(character.id)
        derived = await self.stats_service.compute_derived(character)

        response = CharacterResponse.model_validate(character)
        response.ability_scores = AbilityScoresResponse.model_validate(cache_row) if cache_row is not None else None
        response.hit_dice = derived.hit_dice
        response.speed = derived.speed
        return response
