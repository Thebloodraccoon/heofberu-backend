"""
Spell availability endpoints: class/subclass/race/subrace availability
management (query-style ID — the spell is identified by the required
``spell_id`` query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.spells.availability.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SubclassAvailabilityUpdate,
    SubraceAvailabilityUpdate,
)
from app.features.spells.crud.schemas import SpellResponse
from app.features.spells.dependencies import SpellAvailabilityDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{spell_id:int}/classes",
    response_model=SpellResponse,
    summary="Replace a spell's available classes",
    responses={
        400: {"description": "One or more class IDs don't correspond to an existing class."},
        404: {"description": "No spell exists with the given ID."},
    },
)
async def set_spell_classes(
    spell_id: int,
    data: Annotated[
        ClassAvailabilityUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Restrict to two classes",
                    "value": {"class_ids": [2, 5]},
                },
                "clear": {
                    "summary": "Clear restriction — unrestricted for all classes",
                    "value": {"class_ids": []},
                },
            },
        ),
    ],
    spell_availability: SpellAvailabilityDep,
    _: GmUserDep,
):
    """
    Replace the set of classes a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of classes for this spell — any class not included is
    removed. Send an empty list to clear the restriction (spell becomes
    available to every class).
    """

    return await spell_availability.set_classes(spell_id, data)


@router.put(
    "/{spell_id:int}/subclasses",
    response_model=SpellResponse,
    summary="Replace a spell's available subclasses",
    responses={
        400: {"description": "One or more subclass IDs don't correspond to an existing subclass."},
        404: {"description": "No spell exists with the given ID."},
    },
)
async def set_spell_subclasses(
    spell_id: int,
    data: Annotated[
        SubclassAvailabilityUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Restrict to two subclasses",
                    "value": {"subclass_ids": [1, 4]},
                },
                "clear": {
                    "summary": "Clear restriction — unrestricted for all subclasses",
                    "value": {"subclass_ids": []},
                },
            },
        ),
    ],
    spell_availability: SpellAvailabilityDep,
    _: GmUserDep,
):
    """
    Replace the set of subclasses a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of subclasses for this spell — any subclass not included
    is removed. Send an empty list to clear the restriction (spell becomes
    available to every subclass).
    """

    return await spell_availability.set_subclasses(spell_id, data)


@router.put(
    "/{spell_id:int}/races",
    response_model=SpellResponse,
    summary="Replace a spell's available races",
    responses={
        400: {"description": "One or more race IDs don't correspond to an existing race."},
        404: {"description": "No spell exists with the given ID."},
    },
)
async def set_spell_races(
    spell_id: int,
    data: Annotated[
        RaceAvailabilityUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Restrict to two races (e.g. innate racial spellcasting)",
                    "value": {"race_ids": [3, 8]},
                },
                "clear": {
                    "summary": "Clear restriction — unrestricted for all races",
                    "value": {"race_ids": []},
                },
            },
        ),
    ],
    spell_availability: SpellAvailabilityDep,
    _: GmUserDep,
):
    """
    Replace the set of races a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of races for this spell — any race not included is
    removed. Send an empty list to clear the restriction (spell becomes
    available to every race).
    """

    return await spell_availability.set_races(spell_id, data)


@router.put(
    "/{spell_id:int}/subraces",
    response_model=SpellResponse,
    summary="Replace a spell's available subraces",
    responses={
        400: {"description": "One or more subrace IDs don't correspond to an existing subrace."},
        404: {"description": "No spell exists with the given ID."},
    },
)
async def set_spell_subraces(
    spell_id: int,
    data: Annotated[
        SubraceAvailabilityUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Restrict to two subraces",
                    "value": {"subrace_ids": [2, 6]},
                },
                "clear": {
                    "summary": "Clear restriction — unrestricted for all subraces",
                    "value": {"subrace_ids": []},
                },
            },
        ),
    ],
    spell_availability: SpellAvailabilityDep,
    _: GmUserDep,
):
    """
    Replace the set of subraces a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of subraces for this spell — any subrace not included is
    removed. Send an empty list to clear the restriction (spell becomes
    available to every subrace).
    """

    return await spell_availability.set_subraces(spell_id, data)
