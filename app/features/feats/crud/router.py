"""Feat endpoints: listing, CRUD, and ASI-choice management."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.base.service import Page
from app.features.feats.dependencies import FeatCrudDep
from app.features.feats.schemas import (
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()

@router.get(
    "",
    response_model=Page[FeatGetAllResponse],
    summary="List feats",
)
async def get_feats(
    feat_service: FeatCrudDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the feat's name.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return a paginated list of feats with `id`, `name`, and the ASI choices
    (`ability_score_increases`). `search` matches the name; response is
    `{items, total, page, size}`.
    Open endpoint.
    """

    return await feat_service.get_all(page=page, size=size, search=search)

@router.get(
    "/{feat_id:int}",
    response_model=FeatResponse,
    summary="Get a feat by ID",
    responses={
        404: {"description": "Feat with id not found."},
    },
)
async def get_feat(feat_id: int, feat_service: FeatCrudDep):
    """
    Return a single feat by ID, with everything about it: base fields and
    ability score increase choices. Cached as a single unit.
    Open endpoint.
    """

    return await feat_service.get_by_id(feat_id)

@router.post(
    "",
    response_model=FeatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a feat",
    responses={
        409: {"description": "A feat with this name already exists."},
    },
)
async def create_feat(
    data: Annotated[
        FeatCreate,
        Body(
            openapi_examples={
                "no_prerequisite": {
                    "summary": "No prerequisite, no ASI (e.g. Alert)",
                    "value": {
                        "name": "Alert",
                        "description": "You gain a +5 bonus to initiative and can't be surprised while conscious.",
                    },
                },
                "with_prerequisite": {
                    "summary": "Ability score prerequisite (e.g. Heavy Armor Master)",
                    "value": {
                        "prerequisite_ability": "STR",
                        "prerequisite_minimum_score": 13,
                        "description": (
                            "While wearing heavy armor, bludgeoning, piercing, and slashing damage "
                            "from nonmagical attacks is reduced by 3."
                        ),
                    },
                },
                "with_asi_choice": {
                    "summary": "Grants a choice of ASI (e.g. Resilient)",
                    "value": {
                        "name": "Resilient",
                        "description": (
                            "Choose one ability score. You gain proficiency in saving throws using the chosen ability."
                        ),
                        "ability_score_increases": [
                            {"ability": "STR", "amount": 1},
                            {"ability": "DEX", "amount": 1},
                            {"ability": "CON", "amount": 1},
                            {"ability": "INT", "amount": 1},
                            {"ability": "WIS", "amount": 1},
                            {"ability": "CHA", "amount": 1},
                        ],
                    },
                },
            },
        ),
    ],
    feat_service: FeatCrudDep,
    _: GmUserDep,
):
    """
    Create a new feat. **GM only.**

    `ability_score_increases` is optional and saved with the feat in a
    single transaction.
    """

    return await feat_service.create_feat(data)

@router.patch(
    "/{feat_id:int}",
    response_model=FeatResponse,
    summary="Update a feat's base fields",
    responses={
        404: {"description": "No feat exists with the given ID."},
        409: {"description": "Another feat already uses the requested name."},
    },
)
async def update_feat(
    feat_id: int,
    data: Annotated[
        FeatUpdate,
        Body(
            openapi_examples={
                "rename": {
                    "summary": "Rename the feat and edit its description",
                    "value": {
                        "name": "Alert",
                        "description": "You gain a +5 bonus to initiative and can't be surprised while conscious.",
                    },
                },
                "add-prerequisite": {
                    "summary": "Set an ability score prerequisite",
                    "value": {
                        "prerequisite_ability": "STR",
                        "prerequisite_minimum_score": 13,
                        "prerequisite_description": "Requires 13 or higher Strength.",
                    },
                },
            }
        ),
    ],
    feat_service: FeatCrudDep,
    _: GmUserDep,
):
    """
    Partially update a feat's base fields. **GM only.**

    Only fields included in the request body are changed; use
    `PUT /feats/{feat_id}/ability-score-increases` for ASI choices.
    """

    return await feat_service.update(feat_id, data)

@router.delete(
    "/{feat_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a feat",
    responses={
        404: {"description": "No feat exists with the given ID."},
        409: {"description": "Feat is still in use by one or more characters or features."},
    },
)
async def delete_feat(feat_id: int, feat_service: FeatCrudDep, _: FounderDep):
    """
    Delete a feat. **Founder only.**

    Also removes its ability score increase choices (cascade); blocked if
    the feat is still granted to one or more characters.
    """

    await feat_service.delete(feat_id)
    return None
