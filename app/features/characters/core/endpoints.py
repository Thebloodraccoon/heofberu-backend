"""Character core endpoints: CRUD, HP updates, and resting."""

from fastapi import APIRouter, Query, status

from app.core.base_service import Page
from app.core.dependencies import CharacterServiceDep, CurrentUserDep
from app.features.characters.core.schemas import HpUpdate, RestRequest
from app.features.characters.schemas import CharacterCreate, CharacterResponse, CharacterUpdate

router = APIRouter(tags=["Characters Core"])


@router.get(
    "/",
    response_model=Page[CharacterResponse],
    summary="List characters",
)
def get_characters(
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
    return character_service.get_characters(current_user, search=search, class_id=class_id, page=page, size=size)


@router.get(
    "/{character_id}",
    response_model=CharacterResponse,
    summary="Get a character by ID",
    responses={
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
def get_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """
    Return a single character by ID.

    GM can view any character. Players can only view their own.

    Ability scores come from the ``character_ability_scores`` cache
    as-is (kept fresh by the write paths that can change them — feat
    grants, level-up ASI, race change); derived combat stats are computed
    fresh on every read.
    """
    return character_service.get_character(character_id, current_user)


@router.post(
    "/",
    response_model=CharacterResponse,
    status_code=201,
    summary="Create a character",
    responses={
        404: {"description": "`class_id`, `race_id`, or `background_id` does not reference an existing record."},
    },
)
def create_character(
    character_data: CharacterCreate, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """
    Create a new character, owned by the caller.

    Any authenticated user (GM or player) can create a character; it is
    always owned by whoever creates it.

    `class_id` is required and must reference an existing class.
    `race_id`/`background_id` are optional but, if provided, must also
    reference existing records.

    On creation, the class's spell slot progression for the character's
    starting `level` is applied immediately, so a level-1 caster already
    has spell slot rows without a follow-up `PATCH` to `/spell-slots`.
    """
    return character_service.create_character(character_data, current_user)


@router.patch(
    "/{character_id}",
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
def update_character(
    character_id: int,
    update_data: CharacterUpdate,
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

    Skill proficiencies, saving throw proficiencies, known spells, and
    attacks are managed through their own dedicated endpoints, not
    through this one.
    """
    return character_service.update_character(character_id, update_data, current_user)


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a character",
    responses={
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
def delete_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """
    Delete a character.

    GM can delete any character. Players can only delete their own.
    """
    character_service.delete_character(character_id, current_user)
    return None


@router.patch(
    "/{character_id}/hp",
    response_model=CharacterResponse,
    summary="Apply damage/healing or set HP directly",
    responses={
        400: {"description": "Both `delta` and an absolute HP value were provided, or neither was."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
def update_character_hp(
    character_id: int,
    data: HpUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Apply damage/healing via a relative delta, or set absolute HP values.

    Provide either `delta` (positive to heal, negative to damage) or one
    or both of `current_hp`/`temp_hp` — not both styles in the same
    request.

    `current_hp` is clamped to `[0, max_hp]`; `temp_hp` is clamped to
    `>= 0`.
    """
    return character_service.update_hp(character_id, data, current_user)


@router.post(
    "/{character_id}/rest",
    response_model=CharacterResponse,
    summary="Take a short or long rest",
    responses={
        422: {"description": "`type` is not one of `short` or `long` (rejected by the schema's Literal type)."},
        403: {"description": "Caller is not the owner and is not a GM."},
        404: {"description": "Character with id not found."},
    },
)
def rest_character(
    character_id: int,
    data: RestRequest,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Take a short or long rest (`{"type": "long"}` or `{"type": "short"}`).

    Long rest: restores `current_hp` to `max_hp`, clears `temp_hp`, and
    resets all spell slots (`used` back to 0).

    Short rest: currently a no-op placeholder. 5e short rests recover HP
    via spent hit dice, which isn't modeled yet, and only certain caster
    subclasses recover slots on a short rest — `"short"` is accepted now
    so the rest-type contract is already in place for when hit dice
    tracking is added.
    """
    return character_service.rest(character_id, data, current_user)
