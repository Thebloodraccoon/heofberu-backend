"""Background starting-equipment endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.auth.dependencies import GmUserDep
from app.features.backgrounds.crud.schemas import BackgroundResponse
from app.features.backgrounds.dependencies import BackgroundItemsDep
from app.features.shared.items.schemas import (
    ChoiceGroupsResponse,
    ChoiceGroupsUpdate,
    SourceItemResponse,
    SourceItemsUpdate,
)

router = APIRouter()


@router.get(
    "/items",
    response_model=list[SourceItemResponse],
    summary="List a background's starting equipment",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_items(background_id: int, background_service: BackgroundItemsDep):
    """Return every starting-equipment entry owned by the background. Open endpoint."""

    return await background_service.list_items(background_id)


@router.put(
    "/items",
    response_model=BackgroundResponse,
    summary="Replace a background's starting equipment",
    responses={
        400: {"description": "One or more item IDs don't correspond to an existing item."},
        404: {"description": "No background exists with the given ID."},
    },
)
async def set_background_items(
    background_id: int,
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
    background_service: BackgroundItemsDep,
    _: GmUserDep,
):
    """
    Replace all starting equipment for a background. **GM only.**

    Full replace (not merge): the given `items` become the complete set;
    send an empty list to clear them all.
    """

    return await background_service.set_items(background_id, data)


@router.get(
    "/choice-groups",
    response_model=ChoiceGroupsResponse,
    summary="List a background's starting-equipment choice groups",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_choice_groups(background_id: int, background_service: BackgroundItemsDep):
    """
    Return every choice group (with nested options) for the background: the
    "pick N from M alternatives" decisions made at character creation.
    Open endpoint.
    """

    return await background_service.list_choice_groups(background_id)


@router.put(
    "/choice-groups",
    response_model=ChoiceGroupsResponse,
    summary="Replace a background's starting-equipment choice groups",
    responses={
        400: {"description": "One or more item IDs don't correspond to an existing item."},
        404: {"description": "No background exists with the given ID."},
    },
)
async def set_background_choice_groups(
    background_id: int,
    data: Annotated[
        ChoiceGroupsUpdate,
        Body(
            openapi_examples={
                "tools": {
                    "summary": "Pick one of two tools",
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
    background_service: BackgroundItemsDep,
    _: GmUserDep,
):
    """
    Replace all choice groups for a background. **GM only.**

    Full replace: any group not included is removed.
    """

    return await background_service.set_choice_groups(background_id, data)
