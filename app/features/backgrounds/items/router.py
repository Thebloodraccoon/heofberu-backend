"""
Background starting-equipment endpoints (query-style ID — the background
is identified by the required ``background_id`` query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.backgrounds.crud.schemas import BackgroundResponse
from app.features.backgrounds.dependencies import BackgroundItemsDep
from app.features.backgrounds.items.schemas import SourceItemResponse, SourceItemsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/items",
    response_model=list[SourceItemResponse],
    summary="List a background's starting equipment",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_items(background_id: Annotated[int, Query(gt=0)], background_service: BackgroundItemsDep):
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
    background_id: Annotated[int, Query(gt=0)],
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

    Full replace, not merge: the ``items`` in the request body become the
    complete set of starting items this background grants — any item not
    included is removed. Send an empty list to clear them all.
    """

    return await background_service.set_items(background_id, data)
