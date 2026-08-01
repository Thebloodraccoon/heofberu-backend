from sqlalchemy.orm import Session

from app.features.characters.access import get_character_for_user
from app.features.characters.exceptions import InvalidSkillIdsException
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
)
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.characters.schemas import CharacterResponse
from app.features.skills.repository import SkillRepository
from app.features.users.schemas import UserResponse


class CharacterProficiencyService:
    """
    Skill and saving-throw proficiencies for a character.

    Both are full-replacement operations backed by their own association
    tables (via :class:`CharacterRepository`), separate from the core
    character record handled by ``core.CharacterService``.
    """

    def __init__(self, db: Session):
        self.repository = CharacterRepository(db)
        self.skill_repository = SkillRepository(db)

    def set_skill_proficiencies(
        self, character_id: int, data: SkillProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """Fully replace a character's skill proficiencies (with expertise flags)."""

        character = get_character_for_user(self.repository, character_id, current_user)

        skill_ids = [item.skill_id for item in data.skill_proficiencies]
        if skill_ids:
            found_skills = self.skill_repository.get_skills_by_ids(skill_ids)
            found_ids = {skill.id for skill in found_skills}
            missing_ids = [skill_id for skill_id in skill_ids if skill_id not in found_ids]
            if missing_ids:
                raise InvalidSkillIdsException(missing_ids)

        proficiencies = [
            {"skill_id": item.skill_id, "is_expertise": item.is_expertise} for item in data.skill_proficiencies
        ]
        updated_character = self.repository.set_skill_proficiencies(character, proficiencies)
        return CharacterResponse.model_validate(updated_character)

    def set_saving_throw_proficiencies(
        self, character_id: int, data: SavingThrowProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """Fully replace a character's saving throw proficiencies."""

        character = get_character_for_user(self.repository, character_id, current_user)

        updated_character = self.repository.set_saving_throw_proficiencies(character, data.saving_throws)
        return CharacterResponse.model_validate(updated_character)
