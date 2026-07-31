from fastapi import APIRouter, Body, status

from app.core.dependencies import GmUserDep, RaceServiceDep
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceBriefResponse,
    RaceCreate,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
)

router = APIRouter(prefix="/races", tags=["Races"])


@router.get(
    "/",
    response_model=list[RaceResponse],
    summary="List races (full detail)",
)
def get_races(race_service: RaceServiceDep, skip: int = 0, limit: int = 100):
    """
    Return a paginated list of races, each with full detail — including
    ability bonuses and granted skills.

    Open endpoint, no authentication required.

    For a lighter payload (no bonuses/skills), use `GET /races/brief`
    instead.
    """
    return race_service.get_all(skip=skip, limit=limit)


@router.get(
    "/brief",
    response_model=list[RaceBriefResponse],
    summary="List races (minimal fields)",
)
def get_races_brief(race_service: RaceServiceDep, skip: int = 0, limit: int = 100):
    """
    Return a paginated list of races with only `id`, `name`, `size`, and
    `is_homebrew`.

    Open endpoint, no authentication required.

    Does not include ability bonuses or granted skills — use
    `GET /races/{race_id}` for the full record. Intended for dropdowns,
    tables, and similar listing UI where the full payload is unnecessary.
    """
    return race_service.list_brief(skip=skip, limit=limit)


@router.get(
    "/{race_id}",
    response_model=RaceResponse,
    summary="Get a race by ID",
    responses={
        404: {"description": "Race with id not found."},
    },
)
def get_race(race_id: int, race_service: RaceServiceDep):
    """
    Return a single race by ID, with full detail — including ability
    bonuses and granted skills.

    Open endpoint, no authentication required.
    """
    return race_service.get_by_id(race_id)


@router.post(
    "/",
    response_model=RaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a race",
    responses={
        409: {"description": "A race with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
def create_race(
    race_service: RaceServiceDep,
    current_user: GmUserDep,
    race_data: RaceCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — base fields only",
                "value": {"name": "Elf", "size": "MEDIUM", "speed": 30},
            },
            "with_bonuses_and_skills": {
                "summary": "With ability bonuses and granted skills",
                "value": {
                    "name": "Elf",
                    "size": "MEDIUM",
                    "speed": 30,
                    "traits": "Darkvision, Fey Ancestry",
                    "ability_bonuses": [{"ability": "DEX", "bonus": 2}],
                    "granted_skills": [3, 7],
                },
            },
        },
    ),
):
    """
    Create a new race. **GM only.**

    `ability_bonuses` and `granted_skills` are optional. If provided,
    they're saved together with the race in a single transaction — the
    race is fully set up in one call instead of a `POST` followed by two
    `PUT` calls.
    """
    return race_service.create_race(race_data, created_by_id=current_user.id)


@router.patch(
    "/{race_id}",
    response_model=RaceResponse,
    summary="Update a race's base fields",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Another race already uses the requested name."},
    },
)
def update_race(race_id: int, update_data: RaceUpdate, race_service: RaceServiceDep, _: GmUserDep):
    """
    Partially update a race's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch ability bonuses or granted skills — use
    `PUT /races/{race_id}/ability-bonuses` and `PUT /races/{race_id}/skills`
    for those.
    """
    return race_service.update_race(race_id, update_data)


@router.delete(
    "/{race_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a race",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Race is still in use by one or more characters."},
    },
)
def delete_race(race_id: int, race_service: RaceServiceDep, _: GmUserDep):
    """
    Delete a race. **GM only.**

    Also removes its ability bonuses (cascade) and its links to granted
    skills. Blocked if the race is still assigned to one or more
    characters.
    """
    race_service.delete_race(race_id)
    return None


@router.put(
    "/{race_id}/ability-bonuses",
    response_model=RaceResponse,
    summary="Replace a race's ability bonuses",
    responses={
        404: {"description": "No race exists with the given ID."},
    },
)
def set_race_ability_bonuses(
    race_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: AbilityBonusesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two bonuses",
                "value": {"ability_bonuses": [{"ability": "DEX", "bonus": 2}, {"ability": "INT", "bonus": 1}]},
            },
            "clear": {
                "summary": "Clear all bonuses",
                "value": {"ability_bonuses": []},
            },
        },
    ),
):
    """
    Replace all ability score bonuses for a race. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of bonuses for this race — any bonus not included is
    removed. Send an empty list to clear all bonuses.
    """
    return race_service.set_ability_bonuses(race_id, data)


@router.put(
    "/{race_id}/skills",
    response_model=RaceResponse,
    summary="Replace a race's granted skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No race exists with the given ID."},
    },
)
def set_race_skills(
    race_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: SkillsUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two skills",
                "value": {"skill_ids": [3, 7]},
            },
            "clear": {
                "summary": "Clear all granted skills",
                "value": {"skill_ids": []},
            },
        },
    ),
):
    """
    Replace all granted skills for a race. **GM only.**

    Full replace, not merge: the `skill_ids` in the request body become
    the complete set of skills this race grants — any skill not included
    is removed. Send an empty list to clear all granted skills.
    """
    return race_service.set_skills(race_id, data)
