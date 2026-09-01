"""Subrace CRUD endpoints: listing, get, create, update, delete (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.subraces.crud.schemas import (
    SubraceBriefResponse,
    SubraceCreate,
    SubraceFullResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.features.subraces.dependencies import SubraceCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubraceBriefResponse],
    summary="List a race's subraces",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_subraces(race_id: Annotated[int, Query(gt=0)], race_service: SubraceCrudDep):
    """Return every subrace belonging to the race. Open endpoint."""

    return await race_service.list_for_race(race_id)


@router.post(
    "",
    response_model=SubraceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subrace",
    responses={
        404: {"description": "No race exists with the given ID."},
        409: {"description": "The race already has a subrace with this name."},
    },
)
async def create_subrace(
    data: Annotated[
        SubraceCreate,
        Body(
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
    ],
    race_service: SubraceCrudDep,
    _: GmUserDep,
):
    """Create a subrace under the given race. **GM only.**"""

    return await race_service.create_subrace(data)


@router.get(
    "/{subrace_id:int}",
    response_model=SubraceFullResponse,
    summary="Get a subrace by ID",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def get_subrace(
    subrace_id: int,
    race_service: SubraceCrudDep,
):
    """Return a single subrace with its ability bonuses and features (scoped to the given race). Open endpoint."""

    return await race_service.get_by_id(subrace_id)


@router.patch(
    "/{subrace_id:int}",
    response_model=SubraceResponse,
    summary="Update a subrace's base fields",
    responses={
        404: {"description": "No subrace exists with the given ID under this race."},
        409: {"description": "Another subrace of the same race already uses the requested name."},
    },
)
async def update_subrace(
    subrace_id: int,
    data: Annotated[
        SubraceUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the subrace and edit its description",
                    "value": {
                        "name": "High Elf",
                        "description": "With a keen mind and a mastery of magic.",
                    },
                },
            }
        ),
    ],
    race_service: SubraceCrudDep,
    _: GmUserDep,
):
    """Partially update a subrace's base fields. **GM only.**"""

    return await race_service.update(subrace_id, data)


@router.delete(
    "/{subrace_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subrace",
    responses={
        400: {"description": "The subrace is still assigned to one or more characters."},
        404: {"description": "No subrace exists with the given ID under this race."},
    },
)
async def delete_subrace(
    subrace_id: int,
    race_service: SubraceCrudDep,
    _: FounderDep,
):
    """Delete a subrace. **Founder only.**"""

    await race_service.delete(subrace_id)
    return None
