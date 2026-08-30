"""Subclass CRUD endpoints: listing, get, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.subclasses.crud.schemas import (
    SubclassBriefResponse,
    SubclassCreate,
    SubclassFullResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.subclasses.dependencies import SubclassCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubclassBriefResponse],
    summary="List subclasses",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_subclasses(
    class_id: int | None = Query(None, gt=0, description="Filter by class ID."),
    class_service: SubclassCrudDep = ...,
):
    """Return all subclasses, optionally filtered by ``class_id``. Open endpoint."""

    return await class_service.list_for_class(class_id)


@router.get(
    "/{subclass_id:int}",
    response_model=SubclassFullResponse,
    summary="Get a subclass by ID",
    responses={404: {"description": "Subclass not found."}},
)
async def get_subclass(subclass_id: int, class_service: SubclassCrudDep):
    """Full subclass detail, including its own SUBCLASS-source ``features``. Open endpoint."""

    return await class_service.get_by_id(subclass_id)


@router.post(
    "",
    response_model=SubclassResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subclass",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "A subclass with this name already exists for this class."},
    },
)
async def create_subclass(
    data: Annotated[
        SubclassCreate,
        Body(
            openapi_examples={
                "champion": {
                    "summary": "Fighter — Champion subclass",
                    "value": {
                        "class_id": 1,
                        "name": "Champion",
                        "description": "Pushes physical excellence to its limits.",
                    },
                },
            }
        ),
    ],
    class_service: SubclassCrudDep,
    _: GmUserDep,
):
    """Create a subclass. ``class_id`` is required in the body. **GM only.**"""

    return await class_service.create_subclass(data)


@router.patch(
    "/{subclass_id:int}",
    response_model=SubclassResponse,
    summary="Update a subclass",
    responses={404: {"description": "Subclass not found."}},
)
async def update_subclass(
    subclass_id: int,
    data: Annotated[
        SubclassUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the subclass and edit its description",
                    "value": {
                        "name": "Champion",
                        "description": "Pushes physical excellence to its limits.",
                    },
                },
            }
        ),
    ],
    class_service: SubclassCrudDep,
    _: GmUserDep,
):
    """Partially update a subclass's base fields. **GM only.**"""

    return await class_service.update(subclass_id, data)


@router.delete(
    "/{subclass_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subclass",
    responses={
        403: {"description": "Caller is not the founder."},
        404: {"description": "Subclass not found."},
    },
)
async def delete_subclass(subclass_id: int, class_service: SubclassCrudDep, _: FounderDep):
    """Delete a subclass and all its features. **Founder only.**"""

    await class_service.delete(subclass_id)
    return None
