"""Class CRUD endpoints: listing, get, create, update, delete."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.base.service import Page
from app.features.classes.dependencies import ClassCrudDep
from app.features.classes.schemas import (
    ClassCreate,
    ClassFullResponse,
    ClassGetAllResponse,
    ClassResponse,
    ClassUpdate,
)
from app.features.users.security import FounderDep, GmUserDep

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
    and the `id`/`name` of each subclass, ordered by id.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the class name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching classes across every page, not just this one.

    Does not include primary abilities, saving throws, or available
    skills — use `GET /classes/{class_id}` for the full record.
    """

    return await class_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{class_id:int}",
    response_model=ClassFullResponse,
    summary="Get a class by ID",
    responses={
        404: {"description": "Class with id not found."},
    },
)
async def get_class(class_id: int, class_service: ClassCrudDep):
    """
    Return a single class by ID, with everything about it: base fields,
    primary abilities/saving throws/armor proficiencies/available
    skills/starting items/spell slots, CLASS-source `features`, and every
    `subclass` together with its own SUBCLASS-source features.

    Cached as a single unit, so once warm this is one cache hit instead
    of stitching together separate calls to `.../features`,
    `.../subclasses`, `.../subclasses/{id}/features`, and `.../items`.

    Open endpoint, no authentication required.
    """

    return await class_service.get_by_id(class_id)


@router.post(
    "",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class",
    responses={
        409: {"description": "A class with this name already exists."},
        400: {"description": "Invalid payload (skill IDs, spellcasting_ability consistency, etc.)."},
    },
)
async def create_class(
    data: Annotated[
        ClassCreate,
        Body(
            openapi_examples={
                "fighter": {
                    "summary": "Non-caster, base fields only",
                    "value": {
                        "name": "Fighter",
                        "hit_dice": "D10",
                        "spellcasting_ability": None,
                        "primary_abilities": ["STR"],
                        "saving_throws": ["STR", "CON"],
                    },
                },
                "wizard": {
                    "summary": "Full caster, base fields only",
                    "value": {
                        "name": "Wizard",
                        "hit_dice": "D6",
                        "spellcasting_ability": "INT",
                        "primary_abilities": ["INT"],
                        "saving_throws": ["INT", "WIS"],
                        "available_skills": [3, 7],
                    },
                },
            }
        ),
    ],
    class_service: ClassCrudDep,
    current_user: GmUserDep,
):
    """
    Create a new class. **GM only.**

    `spellcasting_ability` must always be supplied explicitly — pass
    `null` for a non-caster class. If non-null, it must also appear in
    `primary_abilities`.

    `primary_abilities`, `saving_throws`, `armor_proficiencies`, and
    `available_skills` are optional. If provided, they're saved together
    with the class in a single transaction.

    This endpoint is intentionally minimal: it does NOT accept `features`,
    `subclasses`, `spell_slot_progression`, or `starting_items`. Attach
    those afterwards through their own endpoints:
    - `POST /classes/{class_id}/features`
    - `POST /classes/{class_id}/subclasses`
    - `PUT /classes/{class_id}/spell-slots/{class_level}`
    - `PUT /classes/{class_id}/starting-items`
    """

    return await class_service.create_class(data, created_by_id=current_user.id)


@router.patch(
    "/{class_id:int}",
    response_model=ClassResponse,
    summary="Update a class's fields",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "Another class already uses the requested name."},
        400: {
            "description": (
                "spellcasting_ability was set but is not included in primary_abilities, or "
                "primary_abilities was updated without spellcasting_ability and no longer "
                "includes the class's current spellcasting_ability."
            )
        },
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
                    "summary": "Set spellcasting ability alongside primary abilities",
                    "value": {
                        "primary_abilities": ["STR", "INT"],
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
    Partially update a class. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. `primary_abilities` and `saving_throws`, when
    included, are fully replaced (not merged) — the same semantics as the
    dedicated `PUT /classes/{class_id}/saving-throws` endpoint. Does not
    touch available skills — use `PUT /classes/{class_id}/available-skills`
    for that.

    If `primary_abilities` is changed without also passing
    `spellcasting_ability`, the class's current `spellcasting_ability`
    must still be present in the new `primary_abilities` list — otherwise
    the request is rejected. Pass `spellcasting_ability` explicitly in the
    same request to change it alongside `primary_abilities`.
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

    Also removes its primary abilities, saving throws, and links to
    available skills. Blocked if the class is still assigned to one or
    more characters.
    """

    await class_service.delete(class_id)
    return None
