from fastapi import APIRouter

from app.core.dependencies import CharacterProficiencyServiceDep, CurrentUserDep
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
)
from app.features.characters.schemas import CharacterResponse

router = APIRouter(tags=["Characters Proficiencies"])


@router.put("/{character_id}/skills", response_model=CharacterResponse)
def set_character_skill_proficiencies(
    character_id: int,
    data: SkillProficienciesUpdate,
    proficiency_service: CharacterProficiencyServiceDep,
    current_user: CurrentUserDep,
):
    """Fully replace a character's skill proficiencies (with expertise flags)."""

    return proficiency_service.set_skill_proficiencies(character_id, data, current_user)


@router.put("/{character_id}/saving-throws", response_model=CharacterResponse)
def set_character_saving_throws(
    character_id: int,
    data: SavingThrowProficienciesUpdate,
    proficiency_service: CharacterProficiencyServiceDep,
    current_user: CurrentUserDep,
):
    """Fully replace a character's saving throw proficiencies."""

    return proficiency_service.set_saving_throw_proficiencies(character_id, data, current_user)
