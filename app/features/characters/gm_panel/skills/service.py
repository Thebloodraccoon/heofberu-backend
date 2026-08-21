"""GM skill-proficiency service: the only post-creation write path for expertise."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import SkillProficiencyNotFoundException
from app.features.characters.gm_panel.skills.repository import CharacterSkillProficiencyRepository
from app.features.characters.gm_panel.skills.schemas import SkillExpertiseUpdate
from app.features.characters.schemas import SkillProficiencyResponse
from app.features.users.schemas import UserResponse


class GmPanelSkillsService(CharacterSubDomainService):
    """
    Toggle expertise flags on a character's existing skill proficiencies
    (GM-only).

    Expertise is never derived automatically — class feature choices are
    not modeled as selectable options — so a GM sets the flag explicitly
    per proficiency row (e.g. a Rogue's expertise picks). Rows themselves
    are created once at creation (class choices plus background/race
    grants); this capability only flips ``is_expertise`` on an existing
    row, so expertise requires and implies proficiency.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.proficiency_repository = CharacterSkillProficiencyRepository(db)

    async def set_expertise(
        self, character_id: int, skill_id: int, data: SkillExpertiseUpdate, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """Set ``is_expertise`` on one of the character's skill proficiencies."""

        await self.get_character_for_user(character_id, current_user)

        proficiency = await self.proficiency_repository.get_proficiency(character_id, skill_id)
        if proficiency is None:
            raise SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)

        updated = await self.proficiency_repository.set_expertise(proficiency, data.is_expertise)
        await invalidate_character_cache(character_id)
        return SkillProficiencyResponse.model_validate(updated)
