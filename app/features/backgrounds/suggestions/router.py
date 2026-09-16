"""Background suggestion endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.backgrounds.dependencies import BackgroundSuggestionsDep
from app.features.backgrounds.suggestions.schemas import SuggestionCreate, SuggestionResponse, SuggestionUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/suggestions",
    response_model=list[SuggestionResponse],
    summary="List a background's suggestions",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_suggestions(background_id: int, background_service: BackgroundSuggestionsDep):
    """Return every personality-card suggestion owned by the background. Open endpoint."""

    return await background_service.list_suggestions(background_id)


@router.post(
    "/suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a suggestion to a background",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def create_background_suggestion(
    background_id: int,
    data: Annotated[
        SuggestionCreate,
        Body(
            openapi_examples={
                "add": {
                    "summary": "Add a personality trait suggestion",
                    "value": {
                        "suggestion_type": "PERSONALITY_TRAIT",
                        "text": "I idolize a particular hero of my faith.",
                    },
                },
            },
        ),
    ],
    background_service: BackgroundSuggestionsDep,
    _: GmUserDep,
):
    """Add a single suggestion to the background. **GM only.**"""

    return await background_service.create_suggestion(background_id, data)


@router.patch(
    "/suggestions/{suggestion_id}",
    response_model=SuggestionResponse,
    summary="Update a background suggestion",
    responses={404: {"description": "No background or suggestion exists with the given IDs."}},
)
async def update_background_suggestion(
    background_id: int,
    suggestion_id: int,
    data: Annotated[
        SuggestionUpdate,
        Body(
            openapi_examples={
                "update": {
                    "summary": "Change the suggestion's text",
                    "value": {"text": "Tradition. The ancient traditions of worship and sacrifice must be preserved."},
                },
            },
        ),
    ],
    background_service: BackgroundSuggestionsDep,
    _: GmUserDep,
):
    """
    Update an existing suggestion. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """

    return await background_service.update_suggestion(background_id, suggestion_id, data)


@router.delete(
    "/suggestions/{suggestion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a background suggestion",
    responses={404: {"description": "No background or suggestion exists with the given IDs."}},
)
async def delete_background_suggestion(
    background_id: int,
    suggestion_id: int,
    background_service: BackgroundSuggestionsDep,
    _: GmUserDep,
):
    """Remove a single suggestion from the background. **GM only.**"""

    await background_service.delete_suggestion(background_id, suggestion_id)
    return None
