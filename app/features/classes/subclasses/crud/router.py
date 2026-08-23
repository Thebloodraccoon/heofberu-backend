"""Subclass CRUD endpoints: listing, get, create, update, delete."""

from fastapi import APIRouter, Body

from app.features.classes.subclasses.crud.schemas import (
    SubclassBriefResponse,
    SubclassCreate,
    SubclassFullResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.classes.subclasses.dependencies import SubclassCrudDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubclassBriefResponse],
    summary="List subclasses for a class",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_subclasses(class_id: int, class_service: SubclassCrudDep):
    """Return all subclasses for the given class. Open endpoint."""

    return await class_service.list_for_class(class_id)


@router.get(
    "/{subclass_id}",
    response_model=SubclassFullResponse,
    summary="Get a subclass by ID",
    responses={404: {"description": "Class or subclass not found."}},
)
async def get_subclass(class_id: int, subclass_id: int, class_service: SubclassCrudDep):
    """Full subclass detail, including its own SUBCLASS-source `features`. Open endpoint."""

    return await class_service.get_subclass(class_id, subclass_id)


@router.post(
    "",
    response_model=SubclassResponse,
    status_code=201,
    summary="Create a subclass",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "A subclass with this name already exists for this class."},
    },
)
async def create_subclass(
    class_id: int,
    class_service: SubclassCrudDep,
    _: GmUserDep,
    data: SubclassCreate = Body(
        openapi_examples={
            "champion": {
                "summary": "Fighter — Champion subclass with features",
                "value": {
                    "name": "Champion",
                    "archetype_group_name": "Martial Archetypes",
                    "description": "Pushes physical excellence to its limits.",
                },
            },
        }
    ),
):
    """
    Create a subclass for the given class. **GM only.**

    ``features`` are SUBCLASS-source and are created atomically together
    with the subclass.
    """

    return await class_service.create_subclass(class_id, data, created_by_id=_.id)


@router.patch(
    "/{subclass_id}",
    response_model=SubclassResponse,
    summary="Update a subclass",
    responses={404: {"description": "Class or subclass not found."}},
)
async def update_subclass(
    class_id: int, subclass_id: int, data: SubclassUpdate, class_service: SubclassCrudDep, _: GmUserDep
):
    """
    Partially update a subclass's base fields. **GM only.**
    Does not touch features — manage those via the features endpoints.
    """

    return await class_service.update_subclass(class_id, subclass_id, data)


@router.delete(
    "/{subclass_id}",
    status_code=204,
    summary="Delete a subclass",
    responses={404: {"description": "Class or subclass not found."}},
)
async def delete_subclass(class_id: int, subclass_id: int, class_service: SubclassCrudDep, _: GmUserDep):
    """Delete a subclass and all its features. **GM only.**"""

    await class_service.delete_subclass(class_id, subclass_id)
    return None
