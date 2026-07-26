from fastapi import APIRouter, status

from app.core.dependencies import CurrentUserDep, GmUserDep, RaceServiceDep
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
)

router = APIRouter(prefix="/races", tags=["Races"])


@router.get("/", response_model=list[RaceResponse])
def get_races(race_service: RaceServiceDep, _: CurrentUserDep):
    """List all races. Any authenticated user (GM or player) can read."""
    return race_service.get_all_races()


@router.get("/{race_id}", response_model=RaceResponse)
def get_race(race_id: int, race_service: RaceServiceDep, _: CurrentUserDep):
    """Get a single race by ID. Any authenticated user (GM or player) can read."""
    return race_service.get_race_by_id(race_id)


@router.post("/", response_model=RaceResponse, status_code=201)
def create_race(race_data: RaceCreate, race_service: RaceServiceDep, _: GmUserDep):
    """Create a new race. GM only."""
    return race_service.create_race(race_data)


@router.patch("/{race_id}", response_model=RaceResponse)
def update_race(race_id: int, update_data: RaceUpdate, race_service: RaceServiceDep, _: GmUserDep):
    """Update an existing race. GM only."""
    return race_service.update_race(race_id, update_data)


@router.delete("/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_race(race_id: int, race_service: RaceServiceDep, _: GmUserDep):
    """Delete a race. GM only."""
    race_service.delete_race(race_id)
    return None


@router.put("/{race_id}/ability-bonuses", response_model=RaceResponse)
def set_race_ability_bonuses(
    race_id: int,
    data: AbilityBonusesUpdate,
    race_service: RaceServiceDep,
    _: GmUserDep,
):
    """Fully replace the ability score bonuses granted by a race. GM only."""
    return race_service.set_ability_bonuses(race_id, data)


@router.put("/{race_id}/skills", response_model=RaceResponse)
def set_race_skills(
    race_id: int,
    data: SkillsUpdate,
    race_service: RaceServiceDep,
    _: GmUserDep,
):
    """Fully replace the skills granted by a race. GM only."""
    return race_service.set_skills(race_id, data)
