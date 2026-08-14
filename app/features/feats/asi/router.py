"""Feat endpoints: listing, CRUD, and ASI-choice management."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.feats.dependencies import FeatAsiDep
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatResponse,
)

router = APIRouter()


@router.put(
    "/{feat_id}/ability-score-increases",
    response_model=FeatResponse,
    summary="Replace a feat's ability score increase choices",
    responses={
        404: {"description": "No feat exists with the given ID."},
    },
)
async def set_feat_ability_score_increases(
    feat_id: int,
    feat_service: FeatAsiDep,
    _: GmUserDep,
    data: AbilityScoreIncreasesUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two choices",
                "value": {
                    "ability_score_increases": [{"ability": "STR", "amount": 1}, {"ability": "CON", "amount": 1}]
                },
            },
            "clear": {
                "summary": "Clear all ASI choices",
                "value": {"ability_score_increases": []},
            },
        },
    ),
):
    """
    Replace all ability score increase choices for a feat. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of ASI choices for this feat — any choice not included
    is removed. Send an empty list to clear all choices (the feat then
    grants no ability score increase of its own).
    """

    return await feat_service.set_ability_score_increases(feat_id, data)
