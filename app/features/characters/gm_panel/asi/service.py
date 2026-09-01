"""GM free-form ASI adjustment service (no class level attached)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice, MAX_ABILITY_SCORE_CAP
from app.features.characters.ability_score.calculator import TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.asi.schemas import GmAsiChoiceAdd, GmAsiChoiceResponse
from app.features.characters.gm_panel.exceptions import (
    GmAsiAdjustmentNotFoundException,
    LevelTiedAsiChoiceException,
)
from app.features.characters.progression.exceptions import AbilityScoreCapExceededException
from app.features.characters.progression.repository import CharacterASIChoiceRepository
from app.features.users.schemas import UserResponse


class GmPanelAsiService(CharacterSubDomainService):
    """Free-form ±ASI adjustments, independent of any class level (``class_level IS NULL`` rows)."""

    def __init__(self, db: AsyncSession):
        """Wire up the ASI-choice repository and ability-score service."""

        super().__init__(db)
        self.asi_repository = CharacterASIChoiceRepository(db)
        self.stats_service = CharacterStatsService(db)

    async def get_asi_adjustments(self, character_id: int, current_user: UserResponse) -> list[GmAsiChoiceResponse]:
        """List every GM ASI adjustment recorded on a character (level-tied choices excluded)."""

        await self.get_character_for_user(character_id, current_user)
        choices = await self.asi_repository.get_character_choices(character_id)
        return [GmAsiChoiceResponse.model_validate(choice) for choice in choices if choice.class_level is None]

    async def add_asi_adjustment(
        self, character_id: int, data: GmAsiChoiceAdd, current_user: UserResponse
    ) -> GmAsiChoiceResponse:
        """
        Record a free-form ±ability change as an adjustment row with no
        class level, up to ``MAX_ABILITY_SCORE_CAP`` (30).
        """

        character = await self.get_character_for_user(character_id, current_user)

        totals = await self.stats_service.compute(character)
        for item in data.increases:
            current_total = totals[TOTAL_FIELD_BY_ABILITY[item.ability]]
            if current_total + item.amount > MAX_ABILITY_SCORE_CAP:
                raise AbilityScoreCapExceededException(
                    ability=item.ability.value,
                    current_total=current_total,
                    requested=current_total + item.amount,
                )

        async with self._atomic():
            row = await self.asi_repository.add(
                character.id,
                None,
                ASILevelChoice.ASI,
                increases=[{"ability": item.ability.value, "amount": item.amount} for item in data.increases],
                commit=False,
            )

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

        return GmAsiChoiceResponse.model_validate(row)

    async def remove_asi_adjustment(self, character_id: int, adjustment_id: int, current_user: UserResponse) -> bool:
        """Revert one GM ASI adjustment; level-tied choices cannot be removed here."""

        character = await self.get_character_for_user(character_id, current_user)

        choice = await self.asi_repository.get_choice_by_id(character_id, adjustment_id)
        if not choice:
            raise GmAsiAdjustmentNotFoundException(character_id=character_id, adjustment_id=adjustment_id)

        if choice.class_level is not None:
            raise LevelTiedAsiChoiceException(
                character_id=character_id, adjustment_id=adjustment_id, class_level=choice.class_level
            )

        result = await self.asi_repository.remove_choice(choice)

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

        return result
