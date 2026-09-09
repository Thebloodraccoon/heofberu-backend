"""Character grant (feature effect engine) endpoints: pending choices + answering."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.characters.access import get_character_for_user
from app.features.characters.dependencies import CharacterServiceDep, FeatureGrantServiceDep
from app.features.characters.grants.schemas import GrantChoicesUpdate, PendingChoiceGroupsResponse
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/features/{character_feature_id:int}/choices",
    response_model=PendingChoiceGroupsResponse,
    summary="Get a granted feature's pending choice groups",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or feature grant exists with the given ID."},
    },
)
async def get_pending_choice_groups(
    character_id: int,
    character_feature_id: int,
    grant_service: FeatureGrantServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Return the choice groups of a character's feature grant that still need
    the player's picks ("pick N of M"). Grants with no pending groups are
    fully materialized and return an empty ``groups`` list.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.get_pending_choice_groups(character_id, character_feature_id)


@router.patch(
    "/{character_id:int}/features/{character_feature_id:int}/choices",
    response_model=PendingChoiceGroupsResponse,
    summary="Answer a granted feature's choice groups",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or feature grant exists with the given ID."},
        409: {"description": "An option was picked twice for the same group."},
        422: {
            "description": (
                "A group was answered with the wrong number of options, an option "
                "doesn't belong to its group, or an open skill effect lacks a skill_id."
            )
        },
    },
)
async def answer_choice_groups(
    character_id: int,
    character_feature_id: int,
    grant_service: FeatureGrantServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
    data: Annotated[
        GrantChoicesUpdate,
        Body(
            openapi_examples={
                "resilient-con": {
                    "summary": "Resilient feat: choose CON (+1 CON and CON save proficiency)",
                    "value": {
                        "answers": [
                            {
                                "choice_group_id": 1,
                                "choice_option_id": 12,
                            }
                        ]
                    },
                },
                "martial-weapon-skill": {
                    "summary": "A feat choosing proficiency in two skills, one resolved from 'any skill'",
                    "value": {
                        "answers": [
                            {
                                "choice_group_id": 2,
                                "choice_option_id": 30,
                            },
                            {
                                "choice_group_id": 3,
                                "choice_option_id": 41,
                                "skill_id": 7,
                            },
                        ]
                    },
                },
            },
        ),
    ],
):
    """
    Answer (or re-answer) a granted feature's choice groups. Replaces the
    answered groups' stored picks and re-materializes the grant's effect rows
    — skill/saving-throw/armor/weapon proficiencies and granted spells — in
    the same transaction. The response lists any groups still pending.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.answer_choices(character_id, character_feature_id, data)
