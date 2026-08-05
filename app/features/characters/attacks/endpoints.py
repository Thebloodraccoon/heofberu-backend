"""Character attack endpoints: listing and CRUD."""

from fastapi import APIRouter, status

from app.core.dependencies import CharacterAttackServiceDep, CurrentUserDep
from app.features.characters.attacks.schemas import AttackCreate, AttackResponse, AttackUpdate

router = APIRouter(tags=["Characters Attacks"])


@router.get(
    "/{character_id}/attacks",
    response_model=list[AttackResponse],
    summary="List a character's attacks",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
def get_character_attacks(character_id: int, attack_service: CharacterAttackServiceDep, current_user: CurrentUserDep):
    """List all attacks belonging to a character."""
    return attack_service.get_attacks(character_id, current_user)


@router.post(
    "/{character_id}/attacks",
    response_model=AttackResponse,
    status_code=201,
    summary="Add an attack to a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
def create_character_attack(
    character_id: int,
    data: AttackCreate,
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """Add a new attack/weapon entry to a character."""
    return attack_service.create_attack(character_id, data, current_user)


@router.patch(
    "/{character_id}/attacks/{attack_id}",
    response_model=AttackResponse,
    summary="Update an attack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or no attack exists with the given `attack_id`."},
    },
)
def update_character_attack(
    character_id: int,
    attack_id: int,
    data: AttackUpdate,
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """
    Update an existing attack/weapon entry.

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """
    return attack_service.update_attack(character_id, attack_id, data, current_user)


@router.delete(
    "/{character_id}/attacks/{attack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or no attack exists with the given `attack_id`."},
    },
)
def delete_character_attack(
    character_id: int,
    attack_id: int,
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """Remove an attack/weapon entry from a character."""
    attack_service.delete_attack(character_id, attack_id, current_user)
    return None
