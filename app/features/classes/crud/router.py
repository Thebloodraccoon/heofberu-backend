"""Class CRUD endpoints: listing, get, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.base.service import Page
from app.features.auth.dependencies import FounderDep, GmUserDep
from app.features.classes.crud.schemas import (
    ClassCreate,
    ClassGetAllResponse,
    ClassResponse,
    ClassUpdate,
)
from app.features.classes.dependencies import ClassCrudDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[ClassGetAllResponse],
    summary="List classes",
)
async def get_classes(
    class_service: ClassCrudDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the class's name.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of classes with `id`, `name`, `hit_dice`,
    and the `id`/`name` of each subclass, ordered by name.

    `search` is a case-insensitive partial match against the class name.
    `total` is the count across every page.

    Open endpoint.
    """

    return await class_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{class_id:int}",
    response_model=ClassResponse,
    summary="Get a class by ID",
    responses={
        404: {"description": "Class with id not found."},
    },
)
async def get_class(class_id: int, class_service: ClassCrudDep):
    """
    Return a single class by ID with everything about it: base fields,
    saving throws/armor proficiencies/available skills/starting items/spell
    slots, CLASS-source `features`, and every `subclass`.

    Cached as a single unit under the `classes` namespace.

    Open endpoint.
    """

    return await class_service.get_by_id(class_id)


@router.post(
    "",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class",
    responses={
        400: {"description": "A class with this name already exists."},
    },
)
async def create_class(
    data: Annotated[
        ClassCreate,
        Body(
            openapi_examples={
                "fighter": {
                    "summary": "Non-caster, minimal",
                    "value": {
                        "name": "Fighter",
                        "hit_dice": "D10",
                        "spellcasting_ability": None,
                    },
                },
                "wizard": {
                    "summary": "Full caster, minimal",
                    "value": {
                        "name": "Wizard",
                        "hit_dice": "D6",
                        "spellcasting_ability": "INT",
                    },
                },
            }
        ),
    ],
    class_service: ClassCrudDep,
    _: GmUserDep,
):
    """
    Create a new class. **GM only.**

    `spellcasting_ability` must be supplied explicitly (pass `null` for
    a non-caster). `image_url`, when given, must be an absolute http(s) URL
    (the upload endpoint is the usual way to set the image). Base fields
    only — saving throws, proficiencies, available skills, features,
    subclasses, spell slots and starting items are attached afterwards
    through their own endpoints (`PUT /classes/{class_id}/saving-throws`,
    `/armor-proficiencies`, `/weapon-proficiencies`, `/available-skills`,
    `POST /features`, `POST /subclasses`, etc).
    """

    return await class_service.create_class(data)


@router.patch(
    "/{class_id:int}",
    response_model=ClassResponse,
    summary="Update a class's fields",
    responses={
        400: {"description": "Another class already uses the requested name."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def update_class(
    class_id: int,
    data: Annotated[
        ClassUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the class and edit its description",
                    "value": {
                        "name": "Fighter",
                        "description": "A master of weapons and armor.",
                    },
                },
                "make-caster": {
                    "summary": "Set the class's spellcasting ability",
                    "value": {"spellcasting_ability": "INT"},
                },
            }
        ),
    ],
    class_service: ClassCrudDep,
    _: GmUserDep,
):
    """
    Partially update a class. **GM only.**

    Only included fields change; only `spellcasting_ability` accepts an explicit
    `null`. `saving_throws`, when included, is fully replaced (not merged).
    Available skills are untouched.
    """

    return await class_service.update_class(class_id, data)


@router.delete(
    "/{class_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a class",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "Class is still in use by one or more characters."},
    },
)
async def delete_class(class_id: int, class_service: ClassCrudDep, _: FounderDep):
    """
    Delete a class. **Founder only.**

    Also removes its child rows. Blocked if the class is still assigned
    to a character.
    """

    await class_service.delete(class_id)
    return None
