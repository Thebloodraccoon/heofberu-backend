"""GM proficiency endpoints: add/remove/expertise on skill/saving-throw/armor/weapon rows (query-style IDs)."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, status

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency
from app.features.auth.dependencies import GmUserDep
from app.features.characters.gm_panel.dependencies import GmPanelProficienciesDep
from app.features.characters.gm_panel.proficiencies.schemas import (
    ArmorProficiencyAdd,
    SavingThrowProficiencyAdd,
    SkillExpertiseUpdate,
    SkillProficiencyAdd,
    SkillProficiencyResponse,
    WeaponProficiencyAdd,
)
from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
)

router = APIRouter()

_NOT_A_GM: dict[int | str, dict[str, Any]] = {403: {"description": "You are not a GM."}}


@router.post(
    "/proficiencies/skills",
    response_model=SkillProficiencyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a character proficiency in a skill",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists with the given ID."},
        409: {"description": "The character is already proficient."},
    },
)
async def add_character_skill_proficiency(
    character_id: int, data: SkillProficiencyAdd, service: GmPanelProficienciesDep, current_user: GmUserDep
):
    """Grant a free-form skill proficiency (no feature behind it). **GM only.**"""

    return await service.add_skill(character_id, data.skill_id, current_user)


@router.delete(
    "/proficiencies/skills",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a character's proficiency in a skill",
    responses={**_NOT_A_GM, 404: {"description": "No character exists, or it has no proficiency in this skill."}},
)
async def remove_character_skill_proficiency(
    character_id: int,
    skill_id: Annotated[int, Query(gt=0)],
    service: GmPanelProficienciesDep,
    current_user: GmUserDep,
):
    """Revoke a character's proficiency in a skill. **GM only.**"""

    await service.remove_skill(character_id, skill_id, current_user)
    return None


@router.patch(
    "/proficiencies/skills/expertise",
    response_model=SkillProficiencyResponse,
    summary="Toggle expertise on one of a character's skill proficiencies",
    responses={
        **_NOT_A_GM,
        404: {
            "description": (
                "No character exists with the given ID, or the character is not "
                "proficient in this skill (expertise requires proficiency)."
            )
        },
    },
)
async def set_character_skill_expertise(
    character_id: int,
    skill_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        SkillExpertiseUpdate,
        Body(
            openapi_examples={
                "grant": {"summary": "Grant expertise in Stealth", "value": {"is_expertise": True}},
                "revoke": {"summary": "Revoke expertise again", "value": {"is_expertise": False}},
            }
        ),
    ],
    service: GmPanelProficienciesDep,
    current_user: GmUserDep,
):
    """Set or clear the is_expertise flag on a skill proficiency (expertise requires proficiency). **GM only.**"""

    return await service.set_skill_expertise(character_id, skill_id, data, current_user)


@router.post(
    "/proficiencies/saving-throws",
    response_model=CharacterSavingThrowProficiencyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a character proficiency in a saving throw",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists with the given ID."},
        409: {"description": "The character is already proficient."},
    },
)
async def add_character_saving_throw_proficiency(
    character_id: int, data: SavingThrowProficiencyAdd, service: GmPanelProficienciesDep, current_user: GmUserDep
):
    """Grant a free-form saving-throw proficiency. **GM only.**"""

    return await service.add_saving_throw(character_id, data.ability, current_user)


@router.delete(
    "/proficiencies/saving-throws",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a character's proficiency in a saving throw",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists, or it has no proficiency in this saving throw."},
    },
)
async def remove_character_saving_throw_proficiency(
    character_id: int,
    ability: Annotated[AbilityScore, Query()],
    service: GmPanelProficienciesDep,
    current_user: GmUserDep,
):
    """Revoke a character's proficiency in a saving throw. **GM only.**"""

    await service.remove_saving_throw(character_id, ability, current_user)
    return None


@router.post(
    "/proficiencies/armor",
    response_model=CharacterArmorProficiencyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a character proficiency in an armor category",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists with the given ID."},
        409: {"description": "The character is already proficient."},
    },
)
async def add_character_armor_proficiency(
    character_id: int, data: ArmorProficiencyAdd, service: GmPanelProficienciesDep, current_user: GmUserDep
):
    """Grant a free-form armor proficiency. **GM only.**"""

    return await service.add_armor(character_id, data.armor_type, current_user)


@router.delete(
    "/proficiencies/armor",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a character's proficiency in an armor category",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists, or it has no proficiency in this armor category."},
    },
)
async def remove_character_armor_proficiency(
    character_id: int,
    armor_type: Annotated[ArmorProficiency, Query()],
    service: GmPanelProficienciesDep,
    current_user: GmUserDep,
):
    """Revoke a character's proficiency in an armor category. **GM only.**"""

    await service.remove_armor(character_id, armor_type, current_user)
    return None


@router.post(
    "/proficiencies/weapons",
    response_model=CharacterWeaponProficiencyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a character proficiency in a weapon category or a single item",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists with the given ID."},
        409: {"description": "The character is already proficient."},
        422: {"description": "Provide exactly one of weapon_category or item_id."},
    },
)
async def add_character_weapon_proficiency(
    character_id: int, data: WeaponProficiencyAdd, service: GmPanelProficienciesDep, current_user: GmUserDep
):
    """Grant a free-form weapon proficiency — a whole category or a single item. **GM only.**"""

    return await service.add_weapon(
        character_id, current_user, weapon_category=data.weapon_category, item_id=data.item_id
    )


@router.delete(
    "/proficiencies/weapons",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a character's proficiency in a weapon category or a single item",
    responses={
        **_NOT_A_GM,
        404: {"description": "No character exists, or it has no such weapon proficiency."},
        422: {"description": "Provide exactly one of weapon_category or item_id."},
    },
)
async def remove_character_weapon_proficiency(
    character_id: int,
    service: GmPanelProficienciesDep,
    current_user: GmUserDep,
    weapon_category: Annotated[WeaponProficiency | None, Query()] = None,
    item_id: Annotated[int | None, Query(gt=0)] = None,
):
    """Revoke a character's proficiency in a weapon category or a single item. **GM only.**"""

    await service.remove_weapon(character_id, current_user, weapon_category=weapon_category, item_id=item_id)
    return None
