"""Race endpoints: listing, CRUD, ability-bonus/skill, subrace, and feature management."""

from fastapi import APIRouter, Body, Query

from app.constants import RaceSize
from app.core.base_service import Page
from app.core.dependencies import FounderDep, GmUserDep, RaceServiceDep
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.features.races.schemas import (
    AbilityBonusesUpdate,
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
    SkillsUpdate,
    SubraceAbilityBonusesUpdate,
    SubraceCreate,
    SubraceResponse,
    SubraceUpdate,
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

    Also removes its ability bonuses, granted skills, subraces, and
    features (cascade). Blocked if the race is still assigned to one or
    more characters.
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


@router.get(
    "/{race_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a race's features",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_race_features(race_id: int, race_service: RaceServiceDep):
    """Return every feature owned by the race (``source_type: RACE``). Open endpoint."""

    return await race_service.list_features(race_id)


@router.post(
    "/{race_id}/features",
    response_model=NestedFeatureResponse,
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
    applicable) in the same transaction. Returns the created feature.

    ``level`` is not meaningful for race features and must stay ``null``.
    """

    return await race_service.add_feature(race_id, data, created_by_id=_.id)


@router.patch(
    "/{race_id}/features/{feature_id}",
    response_model=NestedFeatureResponse,
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
    are editable; omitted fields are left as-is. Returns the updated
    feature.
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


@router.get(
    "/{race_id}/subraces",
    response_model=list[SubraceResponse],
    summary="List a race's subraces",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_race_subraces(race_id: int, race_service: RaceServiceDep):
    """Return every subrace belonging to the race, with their ability bonuses. Open endpoint."""

    return await race_service.list_subraces(race_id)


@router.post(
    "/{race_id}/subraces",
    response_model=SubraceResponse,
    status_code=201,
    summary="Create a subrace",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "The race already has a subrace with this name."},
    },
)
async def create_race_subrace(
    race_id: int,
    race_service: RaceServiceDep,
    current_user: GmUserDep,
    data: SubraceCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — base fields only",
                "value": {
                    "name": "High Elf",
                    "is_homebrew": "false",
                },
            },
            "with_bonuses_and_features": {
                "summary": "With ability bonuses and features",
                "value": {
                    "name": "High Elf",
                    "is_homebrew": "false",
                    "ability_bonuses": [{"ability": "INT", "bonus": 1}],
                    "features": [
                        {"name": "Elf Weapon Training", "description": "Proficiency with longswords, shortswords, longbows and shortbows."}
                    ],
                },
            },
        },
    ),
):
    """
    Create a subrace under the given race. **GM only.**

    `ability_bonuses` and `features` are optional. If provided, they're
    saved together with the subrace in a single transaction. Subrace
    features are created with ``source_type: SUBRACE`` and auto-grant to
    every character of this subrace.
    """

    return await race_service.create_subrace(race_id, data, created_by_id=current_user.id)


@router.get(
    "/{race_id}/subraces/{subrace_id}",
    response_model=SubraceResponse,
    summary="Get a subrace by ID",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def get_race_subrace(race_id: int, subrace_id: int, race_service: RaceServiceDep):
    """Return a single subrace (scoped to the given race). Open endpoint."""

    return await race_service.get_subrace(race_id, subrace_id)


@router.patch(
    "/{race_id}/subraces/{subrace_id}",
    response_model=SubraceResponse,
    summary="Update a subrace's base fields",
    responses={
        404: {"description": "No subrace exists with the given ID under this race."},
        409: {"description": "Another subrace of the same race already uses the requested name."},
    },
)
async def update_race_subrace(
    race_id: int,
    subrace_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: SubraceUpdate,
):
    """
    Partially update a subrace's base fields. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch ability bonuses or features — use
    `PUT /races/{race_id}/subraces/{subrace_id}/ability-bonuses` and the
    nested `.../features` endpoints for those.
    """

    return await race_service.update_subrace(race_id, subrace_id, data)


@router.delete(
    "/{race_id}/subraces/{subrace_id}",
    status_code=204,
    summary="Delete a subrace",
    responses={
        400: {"description": "The subrace is still assigned to one or more characters."},
        404: {"description": "No subrace exists with the given ID under this race."},
    },
)
async def delete_race_subrace(
    race_id: int,
    subrace_id: int,
    race_service: RaceServiceDep,
    _: FounderDep,
):
    """
    Delete a subrace. **Found-father only.**

    Also removes its ability bonuses and features (cascade). Characters
    pointing at it have ``subrace_id`` set to NULL by the DB, so the
    subrace can be deleted even when assigned — the affected characters
    simply lose their subrace-specific bonuses/features.
    """

    await race_service.delete_subrace(race_id, subrace_id)
    return None


@router.put(
    "/{race_id}/subraces/{subrace_id}/ability-bonuses",
    response_model=SubraceResponse,
    summary="Replace a subrace's ability bonuses",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def set_race_subrace_ability_bonuses(
    race_id: int,
    subrace_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: SubraceAbilityBonusesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with one bonus",
                "value": {"ability_bonuses": [{"ability": "WIS", "bonus": 1}]},
            },
            "clear": {
                "summary": "Clear all bonuses",
                "value": {"ability_bonuses": []},
            },
        },
    ),
):
    """
    Replace all ability score bonuses for a subrace. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of bonuses for this subrace. Send an empty list to clear
    all bonuses.
    """

    return await race_service.set_subrace_ability_bonuses(race_id, subrace_id, data)


@router.get(
    "/{race_id}/subraces/{subrace_id}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subrace's features",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def list_race_subrace_features(race_id: int, subrace_id: int, race_service: RaceServiceDep):
    """Return every feature owned by the subrace (``source_type: SUBRACE``). Open endpoint."""

    return await race_service.list_subrace_features(race_id, subrace_id)


@router.post(
    "/{race_id}/subraces/{subrace_id}/features",
    response_model=NestedFeatureResponse,
    status_code=201,
    summary="Add a feature to a subrace",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def add_race_subrace_feature(
    race_id: int,
    subrace_id: int,
    race_service: RaceServiceDep,
    current_user: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "darkvision": {
                "summary": "Add one feature",
                "value": {
                    "name": "Drow Magic",
                    "description": "Know the dancing lights cantrip.",
                },
            },
        },
    ),
):
    """
    Add one feature to a subrace. **GM only.**

    The feature is created with ``source_type: SUBRACE`` and becomes an
    auto-grant for every character of this subrace in the same
    transaction. Returns the created feature.

    ``level`` is not meaningful for subrace features and must stay ``null``.
    """

    return await race_service.add_subrace_feature(race_id, subrace_id, data, created_by_id=current_user.id)


@router.patch(
    "/{race_id}/subraces/{subrace_id}/features/{feature_id}",
    response_model=NestedFeatureResponse,
    summary="Update one feature of a subrace",
    responses={
        400: {"description": "The feature belongs to a different subrace, or the update is invalid."},
        404: {"description": "No subrace exists with the given ID under this race, or no feature exists with the given ID."},
    },
)
async def update_race_subrace_feature(
    race_id: int,
    subrace_id: int,
    feature_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Drow Magic (Improved)",
                    "description": "Know the dancing lights and faerie fire cantrips.",
                },
            },
        },
    ),
):
    """
    Update one feature of a subrace in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is. Returns the updated
    feature.
    """

    return await race_service.update_subrace_feature(race_id, subrace_id, feature_id, data)


@router.delete(
    "/{race_id}/subraces/{subrace_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a subrace",
    responses={
        400: {"description": "The feature belongs to a different subrace."},
        404: {"description": "No subrace exists with the given ID under this race, or no feature exists with the given ID."},
    },
)
async def remove_race_subrace_feature(
    race_id: int,
    subrace_id: int,
    feature_id: int,
    race_service: RaceServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a subrace. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await race_service.remove_subrace_feature(race_id, subrace_id, feature_id)
    return None
