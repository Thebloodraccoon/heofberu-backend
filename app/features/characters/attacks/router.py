"""
Character attack endpoints: listing and CRUD (query-style IDs).

The router declares no prefix of its own;
``app.features.characters.router`` applies the ``/characters`` prefix —
combined, ``"/attacks"`` resolves to
``/characters/attacks?character_id=...``. The character is identified by
the required ``character_id`` query parameter; per-attack operations
additionally take the ``attack_id`` query parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.attacks.schemas import AttackCreate, AttackResponse, AttackUpdate
from app.features.characters.dependencies import CharacterAttackServiceDep
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/attacks",
    response_model=list[AttackResponse],
    summary="List a character's attacks",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_attacks(
    character_id: int,
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """List all attacks belonging to a character."""

    return await attack_service.get_attacks(character_id, current_user)


@router.post(
    "/{character_id:int}/attacks",
    response_model=AttackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an attack to a character",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def create_character_attack(
    character_id: int,
    data: Annotated[
        AttackCreate,
        Body(
            openapi_examples={
                "melee": {
                    "summary": "A melee longsword attack",
                    "value": {
                        "name": "Longsword",
                        "attack_type": "MELEE_ATTACK",
                        "ability": "STR",
                        "is_proficient": True,
                        "damage_dice_count": 1,
                        "damage_dice_type": "D8",
                        "damage_type": "SLASHING",
                        "bonus_attack": 1,
                        "bonus_damage": 2,
                        "range": "5 ft.",
                    },
                },
                "ranged": {
                    "summary": "A ranged shortbow attack with notes",
                    "value": {
                        "name": "Shortbow",
                        "attack_type": "RANGED_ATTACK",
                        "ability": "DEX",
                        "damage_dice_count": 1,
                        "damage_dice_type": "D6",
                        "damage_type": "PIERCING",
                        "range": "80/320 ft.",
                        "notes": "Ammunition: 20 arrows.",
                    },
                },
            }
        ),
    ],
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """Add a new attack/weapon entry to a character."""

    return await attack_service.create_attack(character_id, data, current_user)


@router.patch(
    "/{character_id:int}/attacks/{attack_id:int}",
    response_model=AttackResponse,
    summary="Update an attack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or no attack exists with the given `attack_id`."},
    },
)
async def update_character_attack(
    character_id: int,
    attack_id: int,
    data: Annotated[
        AttackUpdate,
        Body(
            openapi_examples={
                "update": {
                    "summary": "Switch the attack to DEX and bump its damage bonus",
                    "value": {"ability": "DEX", "bonus_damage": 3},
                },
                "rename-and-note": {
                    "summary": "Rename the weapon and record a note",
                    "value": {"name": "Flame-tongued Longsword", "notes": "Deals an extra 1d6 fire when activated."},
                },
            }
        ),
    ],
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """
    Update an existing attack/weapon entry.

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """

    return await attack_service.update_attack(character_id, attack_id, data, current_user)


@router.delete(
    "/{character_id:int}/attacks/{attack_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or no attack exists with the given `attack_id`."},
    },
)
async def delete_character_attack(
    character_id: int,
    attack_id: int,
    attack_service: CharacterAttackServiceDep,
    current_user: CurrentUserDep,
):
    """Remove an attack/weapon entry from a character."""

    await attack_service.delete_attack(character_id, attack_id, current_user)
    return None
