"""Feat ASI-choice endpoints (the feat is identified by the required ``feat_id``)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.feats.dependencies import FeatAsiDep
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatResponse,
)
from app.features.users.security import GmUserDep

router = APIRouter()

@router.put(
    "/{feat_id:int}/ability-score-increases",
    response_model=FeatResponse,
    summary="Replace a feat's ability score increase choices",
    responses={
        404: {"description": "No feat exists with the given ID."},
    },
)
async def set_feat_ability_score_increases(
    feat_id: int,
    data: Annotated[
        AbilityScoreIncreasesUpdate,
        Body(
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
    ],
    feat_service: FeatAsiDep,
    _: GmUserDep,
):
    """
    Replace all ability score increase choices for a feat. **GM only.**

    Full replace (not merge): the given list becomes the complete set;
    send an empty list to clear all choices.
    """

    return await feat_service.set_ability_score_increases(feat_id, data)
