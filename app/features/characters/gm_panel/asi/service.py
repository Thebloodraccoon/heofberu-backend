"""GM free-form ASI adjustment service (no class level attached)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ASILevelChoice
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
    """
    Free-form ±ASI adjustments, independent of any class level.

    Split out of the former ``CharacterGmPanelService`` — this capability
    owns the GET/POST/DELETE ``/gm-panel/asi`` endpoints. Adjustments are
    recorded ONLY as ``character_asi_choices`` rows with
    ``class_level IS NULL`` (Postgres unique constraint treats NULLs as
    distinct); the base ability columns are never touched — the counted
    increments live in typed child rows and flow into the effective
    totals through the ability-score calculator. Removal is therefore a
    plain row deletion plus cache refresh, and refuses level-tied rows.
    """

    def __init__(self, db: AsyncSession):
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
        class level.

        Unlike the level-up ASI there is no ±budget here — the GM may
        raise or lower abilities through repeated adjustments (negative
        amounts included) — but the ability's effective cap DOES apply
        (20 by default, raised by feature effects such as Primal
        Champion): no adjustment may push an effective total above it.
        The base columns are not touched; the row commits, then the
        ability-score cache refreshes so effective totals follow.
        """

        character = await self.get_character_for_user(character_id, current_user)

        totals = await self.stats_service.compute(character)
        caps = await self.stats_service.resolve_ability_caps(character)
        for item in data.increases:
            current_total = totals[TOTAL_FIELD_BY_ABILITY[item.ability]]
            if current_total + item.amount > caps[item.ability]:
                raise AbilityScoreCapExceededException(
                    ability=item.ability.value,
                    current_total=current_total,
                    requested=current_total + item.amount,
                )

        row = await self.asi_repository.add(
            character.id,
            None,
            ASILevelChoice.ASI,
            increases=[{"ability": item.ability.value, "amount": item.amount} for item in data.increases],
            commit=False,
        )
        await self.repository.db.commit()

        await self.stats_service.refresh(character)
        await invalidate_character_cache(character_id)

        return GmAsiChoiceResponse.model_validate(row)

    async def remove_asi_adjustment(self, character_id: int, adjustment_id: int, current_user: UserResponse) -> bool:
        """
        Revert one GM ASI adjustment by deleting its log row (the counted
        increment children go with it via cascade) and refreshing the
        ability-score cache.

        Level-tied choices (made through level-ups) cannot be removed
        here — they are managed by the progression service.
        """

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
