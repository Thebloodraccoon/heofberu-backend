from fastapi import APIRouter, status

from app.core.dependencies import CharacterServiceDep, CurrentUserDep
from app.features.characters.core.schemas import HpUpdate, RestRequest
from app.features.characters.schemas import CharacterCreate, CharacterResponse, CharacterUpdate

router = APIRouter(prefix="/characters", tags=["Characters"])


@router.get("/", response_model=list[CharacterResponse])
def get_characters(character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """GM gets every character. Players get only their own."""
    return character_service.get_characters(current_user)


@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """GM can view any character. Players can only view their own."""
    return character_service.get_character(character_id, current_user)


@router.post("/", response_model=CharacterResponse, status_code=201)
def create_character(
    character_data: CharacterCreate, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """Any authenticated user (GM or player) can create a character, owned by themselves."""
    return character_service.create_character(character_data, current_user)


@router.patch("/{character_id}", response_model=CharacterResponse)
def update_character(
    character_id: int,
    update_data: CharacterUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """GM can update any character. Players can only update their own."""
    return character_service.update_character(character_id, update_data, current_user)


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """GM can delete any character. Players can only delete their own."""
    character_service.delete_character(character_id, current_user)
    return None


@router.patch("/{character_id}/hp", response_model=CharacterResponse)
def update_character_hp(
    character_id: int,
    data: HpUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Apply damage/healing via a relative delta, or set absolute HP values.

    current_hp is clamped to [0, max_hp]; temp_hp is clamped to >= 0.
    """
    return character_service.update_hp(character_id, data, current_user)


@router.post("/{character_id}/rest", response_model=CharacterResponse)
def rest_character(
    character_id: int,
    data: RestRequest,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Take a short or long rest ({"type": "long"} or {"type": "short"}).

    Long rest: restores current_hp to max_hp, clears temp_hp, and resets all
    spell slots. Short rest: currently a no-op placeholder (see service
    docstring) pending hit-dice tracking.
    """
    return character_service.rest(character_id, data, current_user)
