"""Character proficiency service: the read-only proficiency surface, each resolved with every source that grants it."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyType
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.grants.effects import load_character_grant_effects
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.resolver import (
    ResolvedProficiency,
    feature_entries,
    resolve_all,
    row_entry,
)
from app.features.characters.proficiencies.schemas import (
    ArmorProficiencyView,
    CharacterProficienciesResponse,
    SavingThrowProficiencyView,
    SkillProficiencyView,
    ToolProficiencyView,
    WeaponProficiencyView,
)
from app.features.users.schemas import UserResponse


async def resolve_character_proficiencies(db: AsyncSession, character_id: int) -> list[ResolvedProficiency]:
    """
    Every proficiency the character currently has: its stored rows plus every feature/feat grant's computed
    proficiencies (tagged with the granting feature), resolved together. No access check.
    """

    rows = await CharacterProficiencyRepository(db).get_all(character_id)
    grant_entries = [
        entry
        for feature, effects in await load_character_grant_effects(db, character_id)
        for entry in feature_entries(feature, effects)
    ]
    return resolve_all([*map(row_entry, rows), *grant_entries])


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Read-only proficiency surface for a character: skills, saving throws,
    armor, weapons and tools — each resolved across every contributing source
    (class/race/background choice and GM override rows from
    ``character_proficiencies``, plus feature/feat grants computed from
    their effect tree and the player's picks) into one entry with the full
    list of sources that grants it. Resolution rules live in
    ``proficiencies.resolver``.
    """

    async def get_proficiencies(self, character_id: int, current_user: UserResponse) -> CharacterProficienciesResponse:
        """Resolve every proficiency the character currently has, each with its full list of sources."""

        character = await self.get_character_for_user(character_id, current_user)

        response = CharacterProficienciesResponse()

        for proficiency in await resolve_character_proficiencies(self.repository.db, character.id):
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
                armor_type, item_id = discriminator
                response.armor.append(
                    ArmorProficiencyView(armor_type=armor_type, item_id=item_id, sources=proficiency.sources)
                )
            elif proficiency_type == ProficiencyType.TOOL:
                response.tools.append(ToolProficiencyView(item_id=discriminator[0], sources=proficiency.sources))
            else:
                weapon_category, item_id = discriminator
                response.weapons.append(
                    WeaponProficiencyView(weapon_category=weapon_category, item_id=item_id, sources=proficiency.sources)
                )

        return response
