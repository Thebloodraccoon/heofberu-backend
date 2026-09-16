"""Background suggestion endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.backgrounds.dependencies import BackgroundSuggestionsDep
from app.features.backgrounds.suggestions.schemas import SuggestionResponse, SuggestionsUpdate
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


@router.put(
    "/suggestions",
    response_model=list[SuggestionResponse],
    summary="Replace a background's suggestions",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def set_background_suggestions(
    background_id: int,
    data: Annotated[
        SuggestionsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with a few suggestions",
                    "value": {
                        "suggestions": [
                            {
                                "suggestion_type": "PERSONALITY_TRAIT",
                                "text": "I idolize a particular hero of my faith.",
                            },
                            {
                                "suggestion_type": "IDEAL",
                                "text": "Tradition. The ancient traditions of worship and sacrifice must be preserved.",
                            },
                        ]
                    },
                },
                "clear": {
                    "summary": "Clear all suggestions",
                    "value": {"suggestions": []},
                },
            },
        ),
    ],
    background_service: BackgroundSuggestionsDep,
    _: GmUserDep,
):
    """
    Replace all suggestions for a background. **GM only.**

    Full replace (not merge): the given `suggestions` become the complete
    set; send an empty list to clear them all.
    """

    return await background_service.set_suggestions(background_id, data)
