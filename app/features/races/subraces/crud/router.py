"""Subrace CRUD endpoints: listing, get, create, update, delete."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import FounderDep, GmUserDep
from app.features.races.subraces.crud.schemas import (
    SubraceBriefResponse,
    SubraceCreate,
    SubraceFullResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.features.races.subraces.dependencies import SubraceCrudDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubraceBriefResponse],
    summary="List a race's subraces",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_subraces(race_id: int, race_service: SubraceCrudDep):
    """Return every subrace belonging to the race. Open endpoint."""

    return await race_service.list_for_race(race_id)


@router.post(
    "",
    response_model=SubraceResponse,
    status_code=201,
    summary="Create a subrace",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "The race already has a subrace with this name."},
    },
)
async def create_subrace(
    race_id: int,
    race_service: SubraceCrudDep,
    current_user: GmUserDep,
    data: SubraceCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — base fields only",
                "value": {
                    "name": "High Elf",
                },
            },
            "with_bonuses_and_features": {
                "summary": "With ability bonuses and features",
                "value": {
                    "name": "High Elf",
                    "ability_bonuses": [{"ability": "INT", "bonus": 1}],
                    "features": [
                        {
                            "name": "Elf Weapon Training",
                            "description": "Proficiency with longswords, shortswords, longbows and shortbows.",
                        }
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
    "/{subrace_id}",
    response_model=SubraceFullResponse,
    summary="Get a subrace by ID",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def get_subrace(race_id: int, subrace_id: int, race_service: SubraceCrudDep):
    """Return a single subrace with its ability bonuses and features (scoped to the given race). Open endpoint."""

    return await race_service.get_subrace(race_id, subrace_id)


@router.patch(
    "/{subrace_id}",
    response_model=SubraceResponse,
    summary="Update a subrace's base fields",
    responses={
        404: {"description": "No subrace exists with the given ID under this race."},
        409: {"description": "Another subrace of the same race already uses the requested name."},
    },
)
async def update_subrace(
    race_id: int,
    subrace_id: int,
    race_service: SubraceCrudDep,
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
    "/{subrace_id}",
    status_code=204,
    summary="Delete a subrace",
    responses={
        400: {"description": "The subrace is still assigned to one or more characters."},
        404: {"description": "No subrace exists with the given ID under this race."},
    },
)
async def delete_subrace(
    race_id: int,
    subrace_id: int,
    race_service: SubraceCrudDep,
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
