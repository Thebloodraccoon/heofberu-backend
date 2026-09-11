"""Character proficiency service: the read-only proficiency surface, each row tagged with its source."""

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.character.character_feature_model import CharacterFeature


def _resolve_source(grant: CharacterFeature | None) -> ProficiencySource:
    """Build a row's provenance: the granting feature, or a bare free-form row when there is none."""

    if grant is None:
        return ProficiencySource()
    return ProficiencySource(
        grant_source=grant.grant_source,
        feature_id=grant.feature_id,
        feature_name=grant.feature.name if grant.feature else None,
        feature_source_type=grant.feature.source_type if grant.feature else None,
    )


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Read-only proficiency surface for a character: skills, saving throws,
    armor, and weapons, each annotated with where it came from (a class/
    race/background/feat grant, a GM/ASI grant, or a raw free-form row).
    """

    def __init__(self, db: AsyncSession):
        """Create the proficiency repository alongside the shared character access check."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)

    async def get_proficiencies(
        self, character_id: int, current_user: UserResponse
    ) -> CharacterProficienciesResponse:
        """Fetch every materialized proficiency row for the character, each annotated with its source."""

        character = await self.get_character_for_user(character_id, current_user)

        skills = await self.proficiency_repository.get_skills(character.id)
        saving_throws = await self.proficiency_repository.get_saving_throws(character.id)
        armor = await self.proficiency_repository.get_armor(character.id)
        weapons = await self.proficiency_repository.get_weapons(character.id)

        return CharacterProficienciesResponse(
            skills=[
                SkillProficiencyView(
                    skill_id=row.skill_id,
                    is_expertise=row.is_expertise,
                    source=_resolve_source(row.source_grant),
                )
                for row in skills
            ],
            saving_throws=[
                SavingThrowProficiencyView(ability=row.ability, source=_resolve_source(row.source_grant))
                for row in saving_throws
            ],
            armor=[
                ArmorProficiencyView(armor_type=row.armor_type, source=_resolve_source(row.source_grant))
                for row in armor
            ],
            weapons=[
                WeaponProficiencyView(
                    weapon_category=row.weapon_category,
                    item_id=row.item_id,
                    source=_resolve_source(row.source_grant),
                )
                for row in weapons
            ],
        )
