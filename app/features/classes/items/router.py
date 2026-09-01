"""Class starting-items and choice-group endpoints (query-style ``class_id``)."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.classes.dependencies import ClassItemsDep
from app.features.classes.schemas import ClassResponse
from app.features.shared.items.schemas import (
    ChoiceGroupsResponse,
    ChoiceGroupsUpdate,
    SourceItemResponse,
    SourceItemsUpdate,
)
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/{class_id:int}/items",
    response_model=list[SourceItemResponse],
    summary="List a class's starting equipment",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_items(class_id: int, class_service: ClassItemsDep):
    """Return every starting-equipment entry owned by the class. Open endpoint."""

    return await class_service.list_items(class_id)


@router.put(
    "/{class_id:int}/items",
    response_model=ClassResponse,
    summary="Replace a class's starting equipment",
    responses={
        400: {"description": "One or more item IDs don't correspond to an existing item."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_items(
    class_id: int,
    data: Annotated[
        SourceItemsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two items",
                    "value": {"items": [{"item_id": 1, "quantity": 1}, {"item_id": 5, "quantity": 2}]},
                },
                "clear": {
                    "summary": "Clear all starting equipment",
                    "value": {"items": []},
                },
            },
        ),
    ],
    class_service: ClassItemsDep,
    _: GmUserDep,
):
    """
    Replace all starting equipment for a class. **GM only.**

    Full replace: any item not included is removed.
    """

    return await class_service.set_items(class_id, data)


@router.get(
    "/{class_id:int}/choice-groups",
    response_model=ChoiceGroupsResponse,
    summary="List a class's starting-equipment choice groups",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_choice_groups(
    class_id: int,
    class_service: ClassItemsDep,
):
    """
    Return every choice group (with nested options) for the class — the
    "pick N from M alternatives" decisions made at character creation.

    Open endpoint.
    """

    return await class_service.list_choice_groups(class_id)


@router.put(
    "/{class_id:int}/choice-groups",
    response_model=ChoiceGroupsResponse,
    summary="Replace a class's starting-equipment choice groups",
    responses={
        400: {"description": "One or more item IDs don't correspond to an existing item."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_choice_groups(
    class_id: int,
    data: Annotated[
        ChoiceGroupsUpdate,
        Body(
            openapi_examples={
                "bard_weapons": {
                    "summary": "Bard weapon choice: rapier OR longsword",
                    "value": {
                        "choice_groups": [
                            {
                                "pick_count": 1,
                                "sort_order": 1,
                                "options": [
                                    {"item_id": 10, "quantity": 1},
                                    {"item_id": 20, "quantity": 1},
                                ],
                            }
                        ]
                    },
                },
                "clear": {
                    "summary": "Clear all choice groups",
                    "value": {"choice_groups": []},
                },
            },
        ),
    ],
    class_service: ClassItemsDep,
    _: GmUserDep,
):
    """
    Replace all choice groups for a class. **GM only.**

    Full replace: any group not included is removed.
    """

    return await class_service.set_choice_groups(class_id, data)
