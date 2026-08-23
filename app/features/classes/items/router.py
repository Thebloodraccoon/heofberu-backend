"""Class starting-items endpoints."""

from fastapi import APIRouter, Body

from app.features.classes.dependencies import ClassItemsDep
from app.features.classes.schemas import ClassResponse
from app.features.shared.items.schemas import SourceItemResponse, SourceItemsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/{class_id}/items",
    response_model=list[SourceItemResponse],
    summary="List a class's starting equipment",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_items(class_id: int, class_service: ClassItemsDep):
    """Return every starting-equipment entry owned by the class. Open endpoint."""

    return await class_service.list_items(class_id)


@router.put(
    "/{class_id}/items",
    response_model=ClassResponse,
    summary="Replace a class's starting equipment",
    responses={
        400: {"description": "One or more item IDs don't correspond to an existing item."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_items(
    class_id: int,
    class_service: ClassItemsDep,
    _: GmUserDep,
    data: SourceItemsUpdate = Body(
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
):
    """
    Replace all starting equipment for a class. **GM only.**

    Full replace, not merge: the ``items`` in the request body become the
    complete set of starting items this class grants — any item not
    included is removed. Send an empty list to clear them all.
    """

    return await class_service.set_items(class_id, data)
