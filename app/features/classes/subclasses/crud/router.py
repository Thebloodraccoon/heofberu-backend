"""
Subclass CRUD endpoints: listing, get, create, update, delete
(query-style parent ID).

The router declares no prefix of its own;
``app.features.classes.router`` applies the ``/classes`` prefix and
``app.features.classes.subclasses.router`` the static ``/subclasses``
prefix — combined, ``""`` resolves to ``/classes/subclasses?class_id=...``.The owning class is identified by the required ``class_id`` query
parameter. Mutations additionally take the ``subclass_id`` query
parameter; the detail read keeps the child in the path
(``GET /{subclass_id}?class_id=...``) to avoid colliding with the
listing.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.classes.subclasses.crud.schemas import (
    SubclassBriefResponse,
    SubclassCreate,
    SubclassFullResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.classes.subclasses.dependencies import SubclassCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=list[SubclassBriefResponse],
    summary="List subclasses for a class",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_subclasses(class_id: Annotated[int, Query(gt=0)], class_service: SubclassCrudDep):
    """Return all subclasses for the given class. Open endpoint."""

    return await class_service.list_for_class(class_id)


@router.get(
    "/{subclass_id:int}",
    response_model=SubclassFullResponse,
    summary="Get a subclass by ID",
    responses={404: {"description": "Class or subclass not found."}},
)
async def get_subclass(
    subclass_id: int,
    class_id: Annotated[int, Query(gt=0)],
    class_service: SubclassCrudDep,
):
    """Full subclass detail, including its own SUBCLASS-source `features`. Open endpoint."""

    return await class_service.get_subclass(class_id, subclass_id)


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
    class_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        SubclassCreate,
        Body(
            openapi_examples={
                "champion": {
                    "summary": "Fighter — Champion subclass with features",
                    "value": {
                        "name": "Champion",
                        "description": "Pushes physical excellence to its limits.",
                    },
                },
            }
        ),
    ],
    class_service: SubclassCrudDep,
    current_user: GmUserDep,
):
    """
    Create a subclass for the given class. **GM only.**

    ``features`` are SUBCLASS-source and are created atomically together
    with the subclass.
    """

    return await class_service.create_subclass(class_id, data)


@router.patch(
    "",
    response_model=SubclassResponse,
    summary="Update a subclass",
    responses={404: {"description": "Class or subclass not found."}},
)
async def update_subclass(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
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
    """
    Partially update a subclass's base fields. **GM only.**
    Does not touch features — manage those via the features endpoints.
    """

    return await class_service.update_subclass(class_id, subclass_id, data)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subclass",
    responses={
        403: {"description": "Caller is not the founder."},
        404: {"description": "Class or subclass not found."},
    },
)
async def delete_subclass(
    class_id: Annotated[int, Query(gt=0)],
    subclass_id: Annotated[int, Query(gt=0)],
    class_service: SubclassCrudDep,
    _: FounderDep,
):
    """Delete a subclass and all its features. **Founder only.**"""

    await class_service.delete_subclass(class_id, subclass_id)
    return None
