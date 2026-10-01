"""Subrace CRUD endpoints: listing, get, create, update, delete (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.types import INT32_MAX, EntityIdPath
from app.features.auth.dependencies import FounderDep, GmUserDep
from app.features.subraces.crud.schemas import (
    SubraceCreate,
    SubraceGetAllResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.features.subraces.dependencies import SubraceCrudDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubraceGetAllResponse],
    summary="List a race's subraces",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_subraces(race_id: Annotated[int, Query(gt=0, le=INT32_MAX)], subrace_service: SubraceCrudDep):
    """Return every subrace belonging to the race. Open endpoint."""

    return await subrace_service.list_for_race(race_id)


@router.post(
    "",
    response_model=SubraceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subrace",
    responses={
        404: {"description": "No race exists with the given ID."},
        400: {"description": "The race already has a subrace with this name."},
    },
)
async def create_subrace(
    data: Annotated[
        SubraceCreate,
        Body(
            openapi_examples={
                "minimal": {
                    "summary": "Minimal — name only",
                    "value": {
                        "name": "High Elf",
                        "race_id": 1,
                    },
                },
                "with_description": {
                    "summary": "With a description",
                    "value": {
                        "name": "High Elf",
                        "race_id": 1,
                        "description": "Graceful and quick-witted, with a mastery of magic.",
                    },
                },
            },
        ),
    ],
    subrace_service: SubraceCrudDep,
    _: GmUserDep,
):
    """
    Create a subrace under the given race. **GM only.**

    Base fields only: ``ability_bonuses`` and ``features`` are attached
    afterwards through their own capability endpoints, and ``image_url``
    only via ``PUT /subraces/{id}/image``.
    """

    return await subrace_service.create_subrace(data)


@router.get(
    "/{subrace_id:int}",
    response_model=SubraceResponse,
    summary="Get a subrace by ID",
    responses={404: {"description": "No subrace exists with the given ID."}},
)
async def get_subrace(
    subrace_id: EntityIdPath,
    subrace_service: SubraceCrudDep,
):
    """Return a single subrace with its ability bonuses, tags and features. Open endpoint."""

    return await subrace_service.get_by_id(subrace_id)


@router.patch(
    "/{subrace_id:int}",
    response_model=SubraceResponse,
    summary="Update a subrace's base fields",
    responses={
        404: {"description": "No subrace exists with the given ID."},
        400: {"description": "Another subrace of the same race already uses the requested name."},
    },
)
async def update_subrace(
    subrace_id: EntityIdPath,
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
    subrace_service: SubraceCrudDep,
    _: GmUserDep,
):
    """Partially update a subrace's base fields. **GM only.**"""

    return await subrace_service.update(subrace_id, data)


@router.delete(
    "/{subrace_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subrace",
    responses={
        409: {"description": "The subrace is still assigned to one or more characters."},
        404: {"description": "No subrace exists with the given ID."},
    },
)
async def delete_subrace(
    subrace_id: EntityIdPath,
    subrace_service: SubraceCrudDep,
    _: FounderDep,
):
    """Delete a subrace. **Founder only.**"""

    await subrace_service.delete(subrace_id)
    return None
