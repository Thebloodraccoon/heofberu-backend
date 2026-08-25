"""
Character crud endpoints: CRUD, HP updates, and resting.

Top-level resource operations keep the canonical path-ID form
(``GET/PATCH/DELETE /characters/{character_id}``); character-scoped
sub-resources use query-style IDs (``/characters/hp?character_id=...``).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Path, Query, status

from app.core.base.service import Page
from app.features.characters.crud.schemas import HpUpdate, RestRequest
from app.features.characters.dependencies import CharacterServiceDep
from app.features.characters.schemas import (
    CharacterCreate,
    CharacterFeatResponse,
    CharacterFeatureResponse,
    CharacterResponse,
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
    Return characters visible to the caller.

    GM sees every character. Players see only their own. Optional
    `search` (substring on name) and `class_id` filters narrow the
    result; both combine with the access scoping.

    Response is `{items, total, page, size}` — `total` is the count of
    matching characters across every page, not just this one.

    Ability scores reflect the last-computed cache, not a fresh
    recalculation — a character that has never been fetched
    individually (via `GET /{character_id}`) shows base values only.
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
    Return only the characters owned by the caller — regardless of role
    (a GM calling this sees their own characters, not everyone's).

    Same filters and ``{items, total, page, size}`` envelope as
    `GET /characters`.
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
    Return every character of every user. GM-only.

    Same filters and ``{items, total, page, size}`` envelope as
    `GET /characters`.
    """

    return await character_service.get_all_characters(
        gm_user, search=search, class_id=class_id, page=page, size=size
    )


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
    Return a single character by ID.

    GM can view any character. Players can only view their own.

    Ability scores come from the ``character_ability_scores`` cache
    as-is (kept fresh by the write paths that can change them — feat
    grants, level-up ASI, race change); derived combat stats are computed
    fresh on every read.
    """

    return await character_service.get_character(character_id, current_user)


@router.get(
    "/feats",
    response_model=list[CharacterFeatResponse],
    summary="List a character's feats",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_feats(
    character_id: Annotated[int, Query(gt=0)],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """List every feat granted to a character (level-up choices and GM grants alike)."""

    return await character_service.get_feats(character_id, current_user)


@router.get(
    "/features",
    response_model=list[CharacterFeatureResponse],
    summary="List a character's features",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_features(
    character_id: Annotated[int, Query(gt=0)],
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """List every feature recorded on a character (progression auto-grants plus GM records)."""

    return await character_service.get_features(character_id, current_user)


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
                    "summary": "A frail level-1 wizard with a backstory",
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
                        "backstory": "Expelled from the academy for asking the wrong questions.",
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
    Create a new character, owned by the caller.

    Any authenticated user (GM or player) can create a character; it is
    always owned by whoever creates it. Creation is one-shot at level 1:
    the payload carries no `level`/HP fields (unknown fields are rejected
    with a 422) — `level` is pinned to 1, and starting HP is derived
    from the class hit die + CON modifier. `class_id` is required and
    must reference an existing class; `race_id`/`background_id` are
    optional but, if provided, must reference existing records.

    On creation: `skill_ids` are validated against the class's available
    skills and merged with the background's and the race's granted skills;
    the class's level-1 spell slot progression is applied immediately, so
    a caster already has spell slot totals without any follow-up call.
    Saving throws are not written — they come from the class on every read.
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
    character_id: Annotated[int, Path()],
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
    Partially update a character. GM can update any character; players
    can only update their own.

    Only fields included in the request body are changed; omitted fields
    are left as-is. `class_id`, `race_id`, and `background_id` are not
    editable here — they're set at creation, and neither is `level` (it
    changes through the dedicated level-up endpoint, which also
    re-applies the class's spell slot progression).

    Skill proficiencies are fixed at creation (class choices + background
    grants), saving throws come from the class, and known spells and
    attacks are managed through their own dedicated endpoints — none of
    them are editable here.
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
    "/hp",
    response_model=CharacterResponse,
    summary="Apply damage/healing or set HP directly",
    responses={
        400: {"description": "Both `delta` and an absolute HP value were provided, or neither was."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def update_character_hp(
    character_id: Annotated[int, Query(gt=0)],
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
    Apply damage/healing via a relative delta, or set absolute HP values.

    Provide either `delta` (positive to heal, negative to damage) or one
    or both of `current_hp`/`temp_hp` — not both styles in the same
    request.

    Deltas follow the 5e rules: damage (`delta < 0`) is absorbed by
    `temp_hp` first, with any overflow applied to `current_hp`; healing
    (`delta > 0`) restores `current_hp` only. An absolute `temp_hp` is a
    temp-HP gain — it applies only when higher than the current pool
    (temp HP never stacks); force-set or lower temp HP via a plain
    character PATCH instead.

    `current_hp` is clamped to `[0, max_hp]`; `temp_hp` to `>= 0`.
    """

    return await character_service.update_hp(character_id, data, current_user)


@router.post(
    "/rest",
    response_model=CharacterResponse,
    summary="Take a short or long rest",
    responses={
        422: {"description": "`type` is not one of `short` or `long` (rejected by the schema's Literal type)."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
async def rest_character(
    character_id: Annotated[int, Query(gt=0)],
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

    Long rest: restores `current_hp` to `max_hp` and clears `temp_hp`.
    Known spells and slot totals are unchanged.

    Short rest: currently a no-op placeholder. 5e short rests recover HP
    via spent hit dice, which isn't modeled yet — `"short"` is accepted
    now so the rest-type contract is already in place for when hit dice
    tracking is added.
    """

    return await character_service.rest(character_id, data, current_user)
