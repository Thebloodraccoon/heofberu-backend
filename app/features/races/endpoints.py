"""Race endpoints: listing, CRUD, and ability-bonus/skill management."""

from fastapi import APIRouter, Body, Query

from app.constants import RaceSize
from app.core.base_service import Page
from app.core.dependencies import FounderDep, GmUserDep, RaceServiceDep
from app.features.features.schemas import FeaturesReplace
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
    response_model=Page[RaceResponse],
    summary="List races (full detail)",
)
def get_races(
    race_service: RaceServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    race_size: RaceSize | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of races, each with full detail — including
    ability bonuses and granted skills.

    Open endpoint, no authentication required.

    `race_size` is an exact match (e.g. `race_size=MEDIUM`). `search` is a
    case-insensitive partial match against the race name; both can be
    combined.

    Response is `{items, total, page, size}` — `total` is the count of
    matching races across every page, not just this one.

    For a lighter payload (no bonuses/skills), use `GET /races/brief`
    instead.
    """
    return race_service.get_all(page=page, size=size, filters={"size": race_size}, search=search)


@router.get(
    "/brief",
    response_model=Page[RaceBriefResponse],
    summary="List races (minimal fields)",
)
def get_races_brief(
    race_service: RaceServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    race_size: str | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of races with only `id`, `name`, `size`, and
    `is_homebrew`.

    Open endpoint, no authentication required.

    `race_size` is an exact match (e.g. `race_size=MEDIUM`). `search` is a
    case-insensitive partial match against the race name; both can be
    combined.

    Response is `{items, total, page, size}`, same shape as `GET /races/`.

    Does not include ability bonuses or granted skills — use
    `GET /races/{race_id}` for the full record. Intended for dropdowns,
    tables, and similar listing UI where the full payload is unnecessary.
    """
    return race_service.list_brief(page=page, size=size, filters={"size": race_size}, search=search)


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
    status_code=201,
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
                "value": {
                    "name": "Elf",
                    "size": "MEDIUM",
                    "speed": 30,
                    "is_homebrew": "false",
                },
            },
            "with_bonuses_and_skills": {
                "summary": "With ability bonuses and granted skills",
                "value": {
                    "name": "Elf",
                    "size": "MEDIUM",
                    "speed": 30,
                    "is_homebrew": "false",
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
    return race_service.update(race_id, update_data)


@router.delete(
    "/{race_id}",
    status_code=204,
    summary="Delete a race",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Race is still in use by one or more characters."},
    },
)
def delete_race(race_id: int, race_service: RaceServiceDep, _: FounderDep):
    """
    Delete a race. **Found-father only.**

    Also removes its ability bonuses (cascade) and its links to granted
    skills. Blocked if the race is still assigned to one or more
    characters.
    """
    race_service.delete(race_id)
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


@router.put(
    "/{race_id}/features",
    response_model=RaceResponse,
    summary="Replace a race's features",
    responses={
        400: {"description": "An item's feature id does not belong to this race."},
        422: {"description": "Duplicate feature ids in one request."},
        404: {"description": "No race exists with the given ID."},
    },
)
def replace_race_features(
    race_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: FeaturesReplace = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace the race feature list (matched by id)",
                "value": {
                    "features": [
                        {
                            "id": 3,
                            "name": "Darkvision",
                            "description": "See in dim light as if it were bright light.",
                        },
                        {
                            "name": "Fey Ancestry",
                            "description": "Advantage on saves vs charm.",
                        },
                    ]
                },
            },
            "clear": {
                "summary": "Remove all race features",
                "value": {"features": []},
            },
        },
    ),
):
    """
    Replace a race's feature list. **GM only.**

    Full replace, not merge, matched by feature `id`:

    - items carrying an `id` update that existing feature in place — the
      feature keeps its id, so any character grants (and notes on them)
      survive the update;
    - items without an `id` create new features;
    - current features whose id is not in the request body are deleted,
      which cascades away their character grants.

    Send `{"features": []}` to delete every feature of the race. An `id`
    that doesn't belong to this race is rejected with 400; duplicate ids
    within one request are rejected with 422.
    """
    return race_service.replace_race_features(race_id, data, created_by_id=_.id)
