"""Character proficiency service: the read-only proficiency surface, each resolved with every source that grants it."""

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.schemas import (
    ArmorProficiencyView,
    CharacterProficienciesResponse,
    ProficiencySource,
    SavingThrowProficiencyView,
    SkillProficiencyView,
    WeaponProficiencyView,
)
from app.features.users.schemas import UserResponse
from app.models.character.character_proficiency_model import CharacterProficiency


def _to_source(row: CharacterProficiency) -> ProficiencySource:
    """Build one row's provenance entry."""

    return ProficiencySource(
        source_type=row.source_type,
        feature_id=row.feature_id,
        feature_name=row.feature.name if row.feature else None,
        feature_source_type=row.feature_source_type,
        actor_user_id=row.actor_user_id,
    )


def _group_key(row: CharacterProficiency) -> tuple:
    """The (proficiency_type, *discriminator) key every row of the same proficiency shares."""

    proficiency_type = ProficiencyType(row.proficiency_type)

    if proficiency_type == ProficiencyType.SKILL:
        return (proficiency_type, row.skill_id)
    if proficiency_type == ProficiencyType.SAVING_THROW:
        return (proficiency_type, row.ability)
    if proficiency_type == ProficiencyType.ARMOR:
        return (proficiency_type, row.armor_type)

    return (proficiency_type, row.weapon_category, row.item_id)


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Read-only proficiency surface for a character: skills, saving throws,
    armor, and weapons — each resolved across every contributing row
    (class/race/background choice, feature/feat grant, GM override) into
    one entry with the full list of sources that grant it.

    A GM ``REVOKE`` row excludes the proficiency entirely, regardless of
    how many other sources would otherwise grant it — see
    ``CharacterProficiency`` for the full resolution algorithm.
    """

    def __init__(self, db: AsyncSession):
        """Create the proficiency repository alongside the shared character access check."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)

    async def get_proficiencies(
        self, character_id: int, current_user: UserResponse
    ) -> CharacterProficienciesResponse:
        """Resolve every proficiency the character currently has, each with its full list of sources."""

        character = await self.get_character_for_user(character_id, current_user)
        rows = await self.proficiency_repository.get_all(character.id)

        grouped: dict[tuple, list[CharacterProficiency]] = defaultdict(list)
        for row in rows:
            grouped[_group_key(row)].append(row)

        response = CharacterProficienciesResponse()

        for (proficiency_type, *discriminator), group in grouped.items():
            gm_row = next((row for row in group if row.source_type == ProficiencySourceType.GM), None)
            if gm_row is not None and gm_row.action == ProficiencyAction.REVOKE:
                continue

            sources = [_to_source(row) for row in group]

            if proficiency_type == ProficiencyType.SKILL:
                response.skills.append(
                    SkillProficiencyView(
                        skill_id=discriminator[0],
                        is_expertise=any(row.is_expertise for row in group),
                        sources=sources,
                    )
                )
            elif proficiency_type == ProficiencyType.SAVING_THROW:
                response.saving_throws.append(SavingThrowProficiencyView(ability=discriminator[0], sources=sources))
            elif proficiency_type == ProficiencyType.ARMOR:
                response.armor.append(ArmorProficiencyView(armor_type=discriminator[0], sources=sources))
            else:
                weapon_category, item_id = discriminator
                response.weapons.append(
                    WeaponProficiencyView(weapon_category=weapon_category, item_id=item_id, sources=sources)
                )

        return response
