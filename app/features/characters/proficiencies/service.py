"""Character proficiency service: the read-only proficiency surface, each resolved with every source that grants it."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyType
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.grants.effects import load_character_grant_effects
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.resolver import (
    ProficiencyEntry,
    feature_entries,
    resolve_all,
    row_entry,
)
from app.features.characters.proficiencies.schemas import (
    ArmorProficiencyView,
    CharacterProficienciesResponse,
    SavingThrowProficiencyView,
    SkillProficiencyView,
    WeaponProficiencyView,
)
from app.features.users.schemas import UserResponse


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Read-only proficiency surface for a character: skills, saving throws,
    armor, and weapons — each resolved across every contributing source
    (class/race/background choice and GM override rows from
    ``character_proficiencies``, plus feature/feat grants computed from
    their effect tree and the player's picks) into one entry with the full
    list of sources that grants it. Resolution rules live in
    ``proficiencies.resolver``.
    """

    def __init__(self, db: AsyncSession):
        """Create the proficiency repository alongside the shared character access check."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)

    async def _grant_entries(self, character_id: int) -> list[ProficiencyEntry]:
        """Every feature/feat grant's computed proficiencies, tagged with the granting feature."""

        return [
            entry
            for feature, effects in await load_character_grant_effects(self.repository.db, character_id)
            for entry in feature_entries(feature, effects)
        ]

    async def get_proficiencies(self, character_id: int, current_user: UserResponse) -> CharacterProficienciesResponse:
        """Resolve every proficiency the character currently has, each with its full list of sources."""

        character = await self.get_character_for_user(character_id, current_user)
        rows = await self.proficiency_repository.get_all(character.id)

        response = CharacterProficienciesResponse()

        for proficiency in resolve_all([*map(row_entry, rows), *await self._grant_entries(character.id)]):
            proficiency_type, *discriminator = proficiency.key

            if proficiency_type == ProficiencyType.SKILL:
                response.skills.append(
                    SkillProficiencyView(
                        skill_id=discriminator[0], is_expertise=proficiency.is_expertise, sources=proficiency.sources
                    )
                )
            elif proficiency_type == ProficiencyType.SAVING_THROW:
                response.saving_throws.append(
                    SavingThrowProficiencyView(ability=discriminator[0], sources=proficiency.sources)
                )
            elif proficiency_type == ProficiencyType.ARMOR:
                response.armor.append(ArmorProficiencyView(armor_type=discriminator[0], sources=proficiency.sources))
            else:
                weapon_category, item_id = discriminator
                response.weapons.append(
                    WeaponProficiencyView(weapon_category=weapon_category, item_id=item_id, sources=proficiency.sources)
                )

        return response
