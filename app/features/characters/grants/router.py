"""Character grant (feature effect engine) endpoints: pending choices + answering."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.core.base.repository import _commit_or_rollback
from app.features.characters.access import get_character_for_user
from app.features.characters.dependencies import CharacterServiceDep, FeatureGrantServiceDep
from app.features.characters.grants.schemas import (
    AnsweredChoicesResponse,
    GrantChoicesUpdate,
    PendingChoiceGroupsResponse,
)
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


@router.get(
    "/{character_id:int}/grants/answered",
    response_model=list[AnsweredChoicesResponse],
    summary="List every answered choice across a character's grants",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_all_answered_choices(
    character_id: int,
    grant_service: FeatureGrantServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Character-wide view of every grant that has at least one answered
    choice group, with the option(s) the player actually picked (full
    effect bundle, resolved skill/saving-throw/armor/weapon/spell). Mirrors
    ``GET /grants/pending`` for the answered side; grants with no stored
    pick yet are omitted.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.get_all_answered_choices(character_id)


@router.get(
    "/{character_id:int}/features/{character_feature_id:int}/choices/answered",
    response_model=AnsweredChoicesResponse,
    summary="Get a granted feature's answered choice groups",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or feature grant exists with the given ID."},
    },
)
async def get_answered_choices(
    character_id: int,
    character_feature_id: int,
    grant_service: FeatureGrantServiceDep,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """
    Return the player's resolved picks for one grant's choice groups — the
    option(s) actually chosen, with their full effect bundle. An empty
    ``choices`` list means nothing has been answered yet (see ``GET
    .../choices`` for what's still pending).
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    return await grant_service.get_answered_choices(character_id, character_feature_id)


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
                "doesn't belong to its group, or the picked option carries an open "
                "('any skill'/'any spell') effect — not resolvable via the API yet."
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
                "two-groups": {
                    "summary": "A feat with two independent choice groups, one option each",
                    "value": {
                        "answers": [
                            {
                                "choice_group_id": 2,
                                "choice_option_id": 30,
                            },
                            {
                                "choice_group_id": 3,
                                "choice_option_id": 41,
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
    the same transaction. An option carrying an open ("any skill"/"any
    spell") effect can't be picked yet — the request is rejected (422). The
    response lists any groups still pending.
    """

    await get_character_for_user(character_service.repository, character_id, current_user)
    response = await grant_service.answer_choices(character_id, character_feature_id, data)
    await _commit_or_rollback(grant_service.db)
    return response
