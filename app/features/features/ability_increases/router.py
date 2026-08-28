"""
Feature ability-increase endpoints (query-style ID — the feature is
identified by the required ``feature_id`` query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.features.ability_increases.schemas import (
    AbilityIncreasesUpdate,
    FeatureAbilityIncreasesResponse,
)
from app.features.features.dependencies import FeatureAbilityIncreasesDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.get(
    "/{feature_id:int}/ability-increases",
    response_model=FeatureAbilityIncreasesResponse,
    summary="List a feature's fixed ability-score increases",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature_ability_increases(
    feature_id: int,
    service: FeatureAbilityIncreasesDep,
):
    """List the fixed ability-score effects granted while this feature is on a character. Open endpoint."""

    return await service.get_ability_increases(feature_id)


@router.put(
    "/{feature_id:int}/ability-increases",
    response_model=FeatureAbilityIncreasesResponse,
    summary="Replace a feature's fixed ability-score increases",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No feature exists with the given ID."},
        422: {"description": "Duplicate ability in `ability_increases`."},
    },
)
async def set_feature_ability_increases(
    feature_id: int,
    data: Annotated[
        AbilityIncreasesUpdate,
        Body(
            openapi_examples={
                "primal-champion": {
                    "summary": "Primal Champion: +4 STR and CON, both capped at 24",
                    "value": {
                        "ability_increases": [
                            {"ability": "STR", "amount": 4, "new_cap": 24},
                            {"ability": "CON", "amount": 4, "new_cap": 24},
                        ]
                    },
                },
                "clear": {
                    "summary": "Clear all effects",
                    "value": {"ability_increases": []},
                },
            },
        ),
    ],
    service: FeatureAbilityIncreasesDep,
    _: GmUserDep,
):
    """
    Replace all fixed ability-score increases for a feature. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of effects for this feature — any effect not included is
    removed. Send an empty list to clear them all (the feature then has no
    stat effect). Effects apply automatically to every character the
    feature is granted to; ``new_cap`` raises that ability's maximum score
    above the standard 20.
    """

    return await service.set_ability_increases(feature_id, data)
