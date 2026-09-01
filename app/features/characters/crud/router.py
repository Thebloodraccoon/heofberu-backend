"""
Character crud endpoints: CRUD, HP updates, and resting.

Top-level resource operations keep the canonical path-ID form
(``GET/PATCH/DELETE /characters/{character_id}``); character-scoped
sub-resources use query-style IDs (``/characters/hp?character_id=...``).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.core.base.service import Page
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.dependencies import CharacterServiceDep
from app.features.characters.schemas import (
    CharacterCreate,
    CharacterFeatResponse,
    CharacterFeatureResponse,
    CharacterItemResponse,
    CharacterResponse,
    CharacterStatsResponse,
    CharacterUpdate,
)
from app.features.users.security import CurrentUserDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[CharacterResponse],
    summary="List characters",
)
async def get_characters(
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the character's name.",
    ),
    class_id: int | None = Query(
        None,
        description="Filter to characters of this class.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return characters visible to the caller as a `{items, total, page,
    size}` envelope; optional `search` and `class_id` filters narrow it.

    GM sees every character. Players see only their own.
    """

    return await character_service.get_characters(current_user, search=search, class_id=class_id, page=page, size=size)


@router.get(
    "/mine",
    response_model=Page[CharacterResponse],
    summary="List the current user's characters",
)
async def get_my_characters(
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the character's name.",
    ),
    class_id: int | None = Query(
        None,
        description="Filter to characters of this class.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return only the characters owned by the caller, in the same envelope
    and with the same filters as `GET /characters`.

    Regardless of role (a GM calling this sees their own characters, not
    everyone's).
    """

    return await character_service.get_my_characters(
        current_user, search=search, class_id=class_id, page=page, size=size
    )


@router.get(
    "/all",
    response_model=Page[CharacterResponse],
    summary="List every user's characters",
    responses={
        403: {"description": "Caller is not a GM."},
    },
)
async def get_all_characters(
    character_service: CharacterServiceDep,
    gm_user: GmUserDep,
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against the character's name.",
    ),
    class_id: int | None = Query(
        None,
        description="Filter to characters of this class.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """
    Return every character of every user, with the same filters and
    envelope as `GET /characters`.

    GM only.
    """

    return await character_service.get_all_characters(gm_user, search=search, class_id=class_id, page=page, size=size)


@router.get(
    "/{character_id:int}",
    response_model=CharacterResponse,
    summary="Get a character by ID",
    responses={
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def get_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """
    Return a single character by ID. Ability scores come from the
    ``character_ability_scores`` cache as-is; derived stats are computed
    fresh on every read.

    GM can view any character. Players can only view their own.
    """

    return await character_service.get_character(character_id, current_user)


@router.get(
    "/{character_id:int}/feats",
    response_model=list[CharacterFeatResponse],
    summary="List a character's feats",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_feats(
    character_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """List every feat granted to a character (level-up choices and GM grants alike)."""

    return await character_service.get_feats(character_id, current_user)


@router.get(
    "/{character_id:int}/stats",
    response_model=CharacterStatsResponse,
    summary="Ability scores with their source breakdown",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_stats(
    character_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Return each ability as `{base, total, contributions}` — the ORIGINAL
    base value next to its COMPUTED total and the sources that produced
    it, freshly calculated (never the stale cache).
    """

    return await character_service.get_stats(character_id, current_user)


@router.get(
    "/{character_id:int}/features",
    response_model=list[CharacterFeatureResponse],
    summary="List a character's features",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_features(
    character_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """List every feature recorded on a character (progression auto-grants plus GM records)."""

    return await character_service.get_features(character_id, current_user)


@router.get(
    "/{character_id:int}/items",
    response_model=list[CharacterItemResponse],
    summary="List a character's items",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_items(
    character_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """List every item stack owned by a character (GM/owner readable)."""

    return await character_service.get_items(character_id, current_user)


@router.post(
    "",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a character",
    responses={
        404: {"description": "`class_id`, `race_id`, or `background_id` does not reference an existing record."},
    },
)
async def create_character(
    data: Annotated[
        CharacterCreate,
        Body(
            openapi_examples={
                "fighter": {
                    "summary": "A sturdy level-1 fighter",
                    "value": {
                        "name": "Baldric Ironfist",
                        "class_id": 1,
                        "race_id": 2,
                        "background_id": 3,
                        "strength": 16,
                        "dexterity": 12,
                        "constitution": 14,
                        "intelligence": 8,
                        "wisdom": 10,
                        "charisma": 12,
                        "skill_ids": [1, 5],
                        "armor_class": 16,
                        "shield": 2,
                        "personality_traits": "Gruff but loyal.",
                    },
                },
                "wizard": {
                    "summary": "A frail level-1 wizard with a note",
                    "value": {
                        "name": "Elyse Moonbrook",
                        "class_id": 5,
                        "race_id": 1,
                        "strength": 8,
                        "dexterity": 14,
                        "constitution": 12,
                        "intelligence": 16,
                        "wisdom": 12,
                        "charisma": 10,
                        "notes": "Expelled from the academy for asking the wrong questions.",
                        "money_gold": 10,
                    },
                },
            }
        ),
    ],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Create a new character, owned by the caller. Creation is one-shot at
    level 1: the payload carries no `level`/HP fields (unknown fields are
    rejected with a 422), `class_id` is required, and starting HP/feat/
    skill/equipment are derived or validated server-side.

    Any authenticated user (GM or player) can create a character.
    """

    return await character_service.create_character(data, current_user)


@router.patch(
    "/{character_id:int}",
    response_model=CharacterResponse,
    summary="Update a character",
    responses={
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {
            "description": (
                "Character with id not found, or `class_id`/`race_id`/`background_id` "
                "does not reference an existing record."
            )
        },
    },
)
async def update_character(
    character_id: int,
    data: Annotated[
        CharacterUpdate,
        Body(
            openapi_examples={
                "update": {
                    "summary": "Rename the character and adjust AC",
                    "value": {"name": "Baldric of the Ironfist Clan", "armor_class": 18, "shield": 0},
                },
                "money-and-notes": {
                    "summary": "Record loot and a session note",
                    "value": {
                        "money_gold": 150,
                        "money_silver": 25,
                        "notes": "Owed 20 gp by the innkeeper in Harrowdale.",
                    },
                },
            }
        ),
    ],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Partially update a character: only included fields change. `class_id`,
    `race_id`, and `background_id` are not editable here, nor is `level`.

    GM can update any character; players can only update their own.
    """

    return await character_service.update_character(character_id, data, current_user)


@router.delete(
    "/{character_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a character",
    responses={
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def delete_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """
    Delete a character.

    GM can delete any character. Players can only delete their own.
    """

    await character_service.delete_character(character_id, current_user)
    return None


@router.patch(
    "/{character_id:int}/hp",
    response_model=CharacterResponse,
    summary="Apply damage/healing or set HP directly",
    responses={
        400: {"description": "Both `delta` and an absolute HP value were provided, or neither was."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def update_character_hp(
    character_id: int,
    data: Annotated[
        HpUpdate,
        Body(
            openapi_examples={
                "damage": {
                    "summary": "Take 12 damage (absorbed by temp HP first)",
                    "value": {"delta": -12},
                },
                "set-absolute": {
                    "summary": "Set current and temporary HP directly",
                    "value": {"current_hp": 18, "temp_hp": 5},
                },
            }
        ),
    ],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Apply damage/healing via a relative `delta`, or set absolute HP values
    (not both). Deltas follow 5e rules: damage drains `temp_hp` first;
    healing restores `current_hp` only; absolute `temp_hp` applies only
    when higher than the current pool.
    """

    return await character_service.update_hp(character_id, data, current_user)


@router.post(
    "/{character_id:int}/rest",
    response_model=CharacterResponse,
    summary="Take a short or long rest",
    responses={
        422: {"description": "`type` is not one of `short` or `long` (rejected by the schema's Literal type)."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def rest_character(
    character_id: int,
    data: Annotated[
        RestRequest,
        Body(
            openapi_examples={
                "long-rest": {
                    "summary": "Take a long rest (full heal, temp HP cleared)",
                    "value": {"type": "long"},
                },
                "short-rest": {
                    "summary": "Take a short rest (currently a no-op placeholder)",
                    "value": {"type": "short"},
                },
            }
        ),
    ],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Take a short or long rest (`{"type": "long"}` or `{"type": "short"}`).
    Long rest restores `current_hp` to `max_hp` and clears `temp_hp`;
    short rest is currently a no-op placeholder until hit dice are tracked.
    """

    return await character_service.rest(character_id, data, current_user)
