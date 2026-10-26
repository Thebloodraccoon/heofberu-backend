"""Character combat-stats service: the computed AC and speeds, next to the sheet's manual values."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.ability_score.calculator import DEFAULT_SPEED, TOTAL_FIELD_BY_ABILITY
from app.features.characters.ability_score.service import CharacterStatsService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.combat.calculator import (
    BASE_SPEED_LABEL,
    collect_effects,
    compute_armor_class,
    compute_speeds,
)
from app.features.characters.combat.repository import CombatRepository
from app.features.characters.combat.schemas import (
    ArmorClassView,
    CharacterCombatStatsResponse,
    CombatContribution,
    ComputedSpeeds,
    SpeedView,
)
from app.features.characters.grants.effects import load_character_grant_effects
from app.features.characters.items.repository import CharacterItemRepository
from app.features.users.schemas import UserResponse


def _contributions(lines) -> list[CombatContribution]:
    return [
        CombatContribution(
            source=line.source,
            label=line.label,
            value=line.value,
            speed_type=line.speed_type,
            reason=line.reason,
            reason_code=line.reason_code,
        )
        for line in lines
    ]


class CharacterCombatService(CharacterSubDomainService):
    """
    Computes AC and speeds on every read (uncached, like ``/stats``) from the ability totals, the race's
    speed, the equipped items and the speed/AC effects of the character's grants and active items; the
    character's ``armor_class``/``shield``/``speed`` columns stay the player's manual values.
    """

    def __init__(self, db: AsyncSession):
        """Wire up the stats service and the repositories."""

        super().__init__(db)
        self.stats_service = CharacterStatsService(db)
        self.item_repository = CharacterItemRepository(db)
        self.combat_repository = CombatRepository(db)

    async def get_combat_stats(self, character_id: int, current_user: UserResponse) -> CharacterCombatStatsResponse:
        """The character's manual and computed AC and speeds (owner / campaign GM / founder)."""

        character = await self.get_character_for_user(character_id, current_user)

        cache_row = await self.stats_service.get_or_stale(character.id)
        raw = (
            {field: getattr(cache_row, field) for field in TOTAL_FIELD_BY_ABILITY.values()}
            if cache_row is not None
            else await self.stats_service.compute(character)
        )
        totals = {ability: raw[field] for ability, field in TOTAL_FIELD_BY_ABILITY.items()}
        race_name, race_speed = await self.combat_repository.race_name_and_speed(character.race_id) or (
            BASE_SPEED_LABEL,
            DEFAULT_SPEED,
        )

        equipped, speed_effects, ac_effects = collect_effects(
            await load_character_grant_effects(self.repository.db, character.id),
            await self.item_repository.get_equipped_stacks(character.id),
        )

        armor_class = compute_armor_class(totals, character.level, equipped, ac_effects)
        speeds = compute_speeds(totals, character.level, race_speed, race_name, equipped, speed_effects)

        return CharacterCombatStatsResponse(
            armor_class=ArmorClassView(
                manual=character.armor_class,
                shield_manual=character.shield,
                computed=armor_class.total,
                breakdown=_contributions(armor_class.breakdown),
                inactive=_contributions(armor_class.inactive),
            ),
            speed=SpeedView(
                manual=character.speed,
                computed=ComputedSpeeds(
                    **{speed_type.value.lower(): value for speed_type, value in speeds.speeds.items()}
                ),
                breakdown=_contributions(speeds.breakdown),
                inactive=_contributions(speeds.inactive),
            ),
        )
