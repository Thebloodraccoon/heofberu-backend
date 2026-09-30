"""GM-panel spell endpoints: grant/revoke a free-form spell (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.gm_panel.dependencies import GmPanelSpellsDep
from app.features.characters.gm_panel.spells.schemas import CharacterGrantedSpellAdd
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.post(
    "/spells",
    response_model=CharacterSpellResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a spell to a character directly",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character or spell exists with the given ID."},
        409: {"description": "The GM already granted this spell to the character."},
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
                "No character exists with the given ID, or the GM never granted this spell to the character directly."
            )
        },
    },
)
async def remove_character_granted_spell(
    character_id: int,
    spell_id: Annotated[int, Query(gt=0)],
    spell_service: GmPanelSpellsDep,
    current_user: GmUserDep,
):
    """
    Revoke a spell the GM granted directly (one of `gm_spells`). Spells from
    feature/feat grants can't be removed here — they go with their grant.
    **GM only.**
    """

    await spell_service.remove_granted_spell(character_id, spell_id, current_user)
    return None
