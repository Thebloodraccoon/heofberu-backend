from fastapi import APIRouter, status

from app.core.dependencies import CurrentUserDep, GmUserDep, SkillServiceDep
from app.features.skills.schemas import SkillCreate, SkillResponse, SkillUpdate

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("/", response_model=list[SkillResponse])
def get_skills(skill_service: SkillServiceDep, _: CurrentUserDep):
    """List all skills. Any authenticated user (GM or player) can read."""
    return skill_service.get_all_skills()


@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: int, skill_service: SkillServiceDep, _: CurrentUserDep):
    """Get a single skill by ID. Any authenticated user (GM or player) can read."""
    return skill_service.get_skill_by_id(skill_id)


@router.post("/", response_model=SkillResponse, status_code=201)
def create_skill(skill_data: SkillCreate, skill_service: SkillServiceDep, _: GmUserDep):
    """Create a new skill. GM only."""
    return skill_service.create_skill(skill_data)


@router.patch("/{skill_id}", response_model=SkillResponse)
def update_skill(skill_id: int, update_data: SkillUpdate, skill_service: SkillServiceDep, _: GmUserDep):
    """Update an existing skill. GM only."""
    return skill_service.update_skill(skill_id, update_data)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, skill_service: SkillServiceDep, _: GmUserDep):
    """Delete a skill. GM only.

    Blocked if the skill is still granted by one or more races
    (raises SkillInUseException, mapped to a 409 by the global exception handler).
    """
    skill_service.delete_skill(skill_id)
    return None
