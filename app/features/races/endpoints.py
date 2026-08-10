"""Race endpoints: listing, CRUD, and ability-bonus/skill management."""

from fastapi import APIRouter, Body, Query

from app.constants import RaceSize
from app.core.base_service import Page
from app.core.dependencies import FounderDep, GmUserDep, RaceServiceDep
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
)

router = APIRouter(prefix="/races", tags=["Races"])


@router.get(
    "",
    response_model=Page[RaceGetAllResponse],
    summary="List races",
)
async def get_races(
    race_service: RaceServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    race_size: RaceSize | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of races with only `id`, `name`, `size`, and
    `is_homebrew`.

    Open endpoint, no authentication required.

    `race_size` is an exact match (e.g. `race_size=MEDIUM`). `search` is a
    case-insensitive partial match against the race name; both can be
    combined.

    Response is `{items, total, page, size}` — `total` is the count of
    matching races across every page, not just this one.

    Does not include ability bonuses or granted skills — use
    `GET /races/{race_id}` for the full record.
    """

    return await race_service.get_all(page=page, size=size, filters={"size": race_size}, search=search)


@router.get(
    "/{race_id}",
    response_model=RaceResponse,
    summary="Get a race by ID",
    responses={
        404: {"description": "Race with id not found."},
    },
)
async def get_race(race_id: int, race_service: RaceServiceDep):
    """
    Return a single race by ID, with full detail — including ability
    bonuses and granted skills.

    Open endpoint, no authentication required.
    """

    return await race_service.get_by_id(race_id)


@router.post(
    "",
    response_model=RaceResponse,
    status_code=201,
    summary="Create a race",
    responses={
        409: {"description": "A race with this name already exists."},
        400: {"description": "One or more `granted_skills` IDs don't correspond to an existing skill."},
    },
)
async def create_race(
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

    return await race_service.create_race(race_data, created_by_id=current_user.id)


@router.patch(
    "/{race_id}",
    response_model=RaceResponse,
    summary="Update a race's base fields",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Another race already uses the requested name."},
    },
)
async def update_race(race_id: int, update_data: RaceUpdate, race_service: RaceServiceDep, _: GmUserDep):
    """
    Partially update a race's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch ability bonuses or granted skills — use
    `PUT /races/{race_id}/ability-bonuses` and `PUT /races/{race_id}/skills`
    for those.
    """

    return await race_service.update(race_id, update_data)


@router.delete(
    "/{race_id}",
    status_code=204,
    summary="Delete a race",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "Race is still in use by one or more characters."},
    },
)
async def delete_race(race_id: int, race_service: RaceServiceDep, _: FounderDep):
    """
    Delete a race. **Found-father only.**

    Also removes its ability bonuses (cascade) and its links to granted
    skills. Blocked if the race is still assigned to one or more
    characters.
    """

    await race_service.delete(race_id)
    return None


@router.put(
    "/{race_id}/ability-bonuses",
    response_model=RaceResponse,
    summary="Replace a race's ability bonuses",
    responses={
        404: {"description": "No race exists with the given ID."},
    },
)
async def set_race_ability_bonuses(
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

    return await race_service.set_ability_bonuses(race_id, data)


@router.put(
    "/{race_id}/skills",
    response_model=RaceResponse,
    summary="Replace a race's granted skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No race exists with the given ID."},
    },
)
async def set_race_skills(
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

    return await race_service.set_skills(race_id, data)


@router.post(
    "/{race_id}/features",
    response_model=RaceResponse,
    status_code=201,
    summary="Add a feature to a race",
    responses={
        404: {"description": "No race exists with the given ID."},
    },
)
async def add_race_feature(
    race_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "darkvision": {
                "summary": "Add one feature",
                "value": {
                    "name": "Darkvision",
                    "description": "See in dim light within 60 ft.",
                },
            },
        },
    ),
):
    """
    Add one feature to a race. **GM only.**

    The feature is created with ``source_type: RACE`` and becomes an
    auto-grant for every character of this race (level-gated where
    applicable) in the same transaction. Returns the updated race.

    ``level`` is not meaningful for race features and must stay ``null``.
    """

    return await race_service.add_feature(race_id, data, created_by_id=_.id)


@router.patch(
    "/{race_id}/features/{feature_id}",
    response_model=RaceResponse,
    summary="Update one feature of a race",
    responses={
        400: {"description": "The feature belongs to a different race, or the update is invalid."},
        404: {"description": "No race exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_race_feature(
    race_id: int,
    feature_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Darkvision (Improved)",
                    "description": "See in dim light within 120 ft.",
                },
            },
        },
    ),
):
    """
    Update one feature of a race in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is.
    """

    return await race_service.update_feature(race_id, feature_id, data)


@router.delete(
    "/{race_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a race",
    responses={
        400: {"description": "The feature belongs to a different race."},
        404: {"description": "No race exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_race_feature(
    race_id: int,
    feature_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a race. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await race_service.remove_feature(race_id, feature_id)
    return None
