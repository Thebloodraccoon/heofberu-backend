from fastapi import APIRouter

from app.core.dependencies import CurrentUserDep, GmUserDep, RaceServiceDep
from app.features.races.schemas import RaceCreate, RaceResponse, RaceUpdate

router = APIRouter()


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
