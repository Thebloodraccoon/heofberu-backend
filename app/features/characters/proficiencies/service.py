"""Character proficiency service: full-replace of skills and saving throws."""

from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
)
from app.features.characters.schemas import CharacterResponse
from app.features.skills.repository import SkillRepository
from app.features.users.schemas import UserResponse


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Skill and saving-throw proficiencies for a character.

    Both are full-replacement operations. Access control is enforced
    against the owning character via the inherited
    ``CharacterSubDomainService`` wiring, but the proficiency rows
    themselves are read/written through
    ``CharacterProficiencyRepository`` since they live in their own
    association tables (``character_skill_proficiencies``,
    ``character_saving_throw_proficiencies``), separate from the core
    character record handled by ``core.CharacterService``.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)
        self.skill_repository = SkillRepository(db)

    def set_skill_proficiencies(
        self, character_id: int, data: SkillProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """
        Fully replace a character's skill proficiencies (with expertise flags).

        Skill IDs are validated through the base layer's ``resolve_ids``
        helper (same path backgrounds/races use for their granted skills):
        any ID that doesn't resolve raises ``RecordIdsInvalidError``, which
        the data-layer handler maps to a 400. The old character-specific
        ``InvalidSkillIdsException`` is gone.
        """

        character = self.get_character_for_user(character_id, current_user)

        skill_ids = [item.skill_id for item in data.skill_proficiencies]
        if skill_ids:
            BaseService.resolve_ids(self.skill_repository.get_skills_by_ids, skill_ids, "Skill")

        proficiencies = [
            {"skill_id": item.skill_id, "is_expertise": item.is_expertise} for item in data.skill_proficiencies
        ]
        updated_character = self.proficiency_repository.set_skill_proficiencies(character, proficiencies)
        return CharacterResponse.model_validate(updated_character)

    def set_saving_throw_proficiencies(
        self, character_id: int, data: SavingThrowProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """Fully replace a character's saving throw proficiencies."""

        character = self.get_character_for_user(character_id, current_user)

        updated_character = self.proficiency_repository.set_saving_throw_proficiencies(character, data.saving_throws)
        return CharacterResponse.model_validate(updated_character)
