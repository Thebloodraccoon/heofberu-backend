"""Character grant (feature effect engine) endpoints: pending choices + answering."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.characters.access import get_character_for_user
from app.features.characters.dependencies import CharacterServiceDep, FeatureGrantServiceDep
from app.features.characters.grants.schemas import GrantChoicesUpdate, PendingChoiceGroupsResponse
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/grants/pending",
    response_model=list[PendingChoiceGroupsResponse],
    summary="List every pending choice across a character's grants",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_all_pending_choices(
    character_id: int,
    grant_service: FeatureGrantServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Character-wide "you still need to choose" surface: every feature/feat
    grant that still has an unanswered choice group, across the whole
    character. Meant to drive a forced picker right after character
    creation or a level-up — poll this once instead of checking each
    grant's own ``/features/{id}/choices`` individually.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.get_all_pending_choices(character_id)


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
                "doesn't belong to its group, or an open skill/spell effect lacks "
                "its resolution (skill_id/spell_id) or resolves to a spell that "
                "violates the school/level filter."
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
                    "summary": "Resilient feat: choose CON (+1 CON)",
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
                "open-spell-filter": {
                    "summary": "A feature whose option grants 'any 1st-level Evocation spell', resolved to spell 9",
                    "value": {
                        "answers": [
                            {
                                "choice_group_id": 4,
                                "choice_option_id": 52,
                                "spell_id": 9,
                            }
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
    the same transaction. Options carrying an open ("any skill") effect need
    ``skill_id``; options carrying an open (school+level-filtered) spell
    effect need ``spell_id``. The response lists any groups still pending.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.answer_choices(character_id, character_feature_id, data)
