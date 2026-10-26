"""Weapon-property dictionary endpoints: list, create, update, delete."""

from fastapi import APIRouter, status

from app.features.auth.dependencies import GmUserDep
from app.features.items.dependencies import WeaponPropertyDep
from app.features.items.properties.schemas import (
    WeaponPropertyCreate,
    WeaponPropertyResponse,
    WeaponPropertyUpdate,
)

router = APIRouter()


@router.get("/properties", response_model=list[WeaponPropertyResponse], summary="List weapon properties")
async def list_weapon_properties(service: WeaponPropertyDep):
    """Every weapon property (Finesse, Light, homebrew ones...), by name. Open endpoint."""

    return await service.list_properties()


@router.post(
    "/properties",
    response_model=WeaponPropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a weapon property",
    responses={409: {"description": "A property with this name already exists."}},
)
async def create_weapon_property(data: WeaponPropertyCreate, service: WeaponPropertyDep, _: GmUserDep):
    """
    Add a property to the dictionary. `requires_range` / `requires_versatile_damage` make a weapon with it
    fill `range_normal` / its two-handed damage. **GM only.**
    """

    return await service.create(data)


@router.patch(
    "/properties/{property_id:int}",
    response_model=WeaponPropertyResponse,
    summary="Update a weapon property",
    responses={404: {"description": "No such property."}, 409: {"description": "The name is taken."}},
)
async def update_weapon_property(
    property_id: int, data: WeaponPropertyUpdate, service: WeaponPropertyDep, _: GmUserDep
):
    """Partially update a property (existing weapons aren't re-checked against new flags). **GM only.**"""

    return await service.update(property_id, data)


@router.delete(
    "/properties/{property_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a weapon property",
    responses={404: {"description": "No such property."}, 409: {"description": "A weapon still has it."}},
)
async def delete_weapon_property(property_id: int, service: WeaponPropertyDep, _: GmUserDep):
    """Delete a property no weapon has. **GM only.**"""

    await service.delete(property_id)
    return None
