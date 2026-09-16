"""GM-panel spell endpoints: grant/revoke a free-form spell (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.gm_panel.dependencies import GmPanelSpellsDep
from app.features.characters.gm_panel.spells.schemas import CharacterGrantedSpellAdd
from app.features.characters.grants.schemas import CharacterGrantedSpellResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.post(
    "/spells",
    response_model=CharacterGrantedSpellResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a spell to a character directly",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character or spell exists with the given ID."},
    },
)
async def add_character_granted_spell(
    character_id: int,
    data: Annotated[
        CharacterGrantedSpellAdd,
        Body(
            openapi_examples={
                "boon": {
                    "summary": "Grant Fireball as a homebrew boon",
                    "value": {"spell_id": 12},
                },
            }
        ),
    ],
    spell_service: GmPanelSpellsDep,
    current_user: GmUserDep,
):
    """
    Grant any spell to a character directly — no class/race eligibility
    check, no feature/feat behind it. **GM only.**
    """

    return await spell_service.add_granted_spell(character_id, data, current_user)


@router.delete(
    "/spells",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a directly-granted spell from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": (
                "No character exists with the given ID, or no free-form granted spell "
                "exists with the given `granted_spell_id`."
            )
        },
        409: {"description": "The granted spell came from a feature/feat grant — revoke that grant instead."},
    },
)
async def remove_character_granted_spell(
    character_id: int,
    granted_spell_id: Annotated[int, Query(gt=0)],
    spell_service: GmPanelSpellsDep,
    current_user: GmUserDep,
):
    """Revoke a free-form (directly-granted) spell from a character. **GM only.**"""

    await spell_service.remove_granted_spell(character_id, granted_spell_id, current_user)
    return None
