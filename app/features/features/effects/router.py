"""Feature effects endpoints: read + diff-based write of a feature's fixed effects and choice groups."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.auth.dependencies import GmUserDep
from app.features.features.dependencies import FeatureEffectsDep
from app.features.features.effects.schemas import (
    ChoiceGroupResponse,
    ChoiceGroupsUpdate,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
)

router = APIRouter()


@router.get(
    "/{feature_id:int}/effects",
    response_model=FeatureEffectsResponse,
    summary="Read a feature's full effect tree (choice groups + fixed effects)",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature_effects(
    feature_id: int,
    service: FeatureEffectsDep,
):
    """Return a feature's choice groups (with their option effect bundles) and its fixed effects. Open endpoint."""

    return await service.get_effects(feature_id)


@router.put(
    "/{feature_id:int}/effects",
    response_model=FeatureEffectsResponse,
    summary="Diff-update a feature's fixed (automatic) effects",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No feature exists with the given ID."},
        422: {
            "description": (
                "Invalid effect payload (duplicates, a fixed skill/spell without its id, out-of-range values, "
                "unknown skill/item/spell id, unknown key), or an item's id doesn't belong to this feature."
            )
        },
    },
)
async def set_feature_effects(
    feature_id: int,
    data: Annotated[
        FeatureEffectsUpdate,
        Body(
            openapi_examples={
                "elf-weapon-training": {
                    "summary": "Elf Weapon Training: fixed proficiency in a longsword and a bow",
                    "value": {
                        "weapon_effects": [
                            {"item_id": 3},
                        ]
                    },
                },
                "resilient-asi-only": {
                    "summary": "A feat that grants +1 CON (fixed, the saving throw rides a choice)",
                    "value": {
                        "ability_effects": [{"ability": "CON", "amount": 1}],
                    },
                },
                "clear": {
                    "summary": "Clear all fixed effects",
                    "value": {
                        "ability_effects": [],
                        "skill_effects": [],
                        "saving_throw_effects": [],
                        "armor_effects": [],
                        "weapon_effects": [],
                        "spell_effects": [],
                    },
                },
            },
        ),
    ],
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """
    Diff-update a feature's fixed effects. **GM only.**

    Every effect type that is **present** in the body becomes the complete
    set of that type, diffed by id: an item with an existing row's ``id``
    updates it in place, an item with no ``id`` inserts a new row, and an
    existing row whose ``id`` is missing from the list is deleted (send ``[]``
    to clear a type). An effect type that is **omitted** is left untouched.
    An ``id`` that doesn't belong to this feature, a repeated id/effect, a
    fixed skill/spell effect without its ``skill_id``/``spell_id`` and an
    unknown skill/item/spell id are all a 422. When something changed, every
    character the feature is granted to is refreshed in the same transaction.
    Choice groups are managed via ``PUT /features/{id}/choice-groups``.
    """

    return await service.set_fixed_effects(feature_id, data)


@router.get(
    "/{feature_id:int}/choice-groups",
    response_model=list[ChoiceGroupResponse],
    summary="Read a feature's choice groups",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature_choice_groups(
    feature_id: int,
    service: FeatureEffectsDep,
):
    """Return a feature's "pick N of M" choice groups with their option effect bundles. Open endpoint."""

    return await service.get_choice_groups(feature_id)


@router.put(
    "/{feature_id:int}/choice-groups",
    response_model=list[ChoiceGroupResponse],
    summary="Diff-update a feature's choice groups",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No feature exists with the given ID."},
        409: {"description": "A removed option/group is still referenced by a character's answered choice."},
        422: {
            "description": (
                "Invalid choice-group payload (pick_count outside 1-50, duplicates, unknown skill/item/spell id, "
                "unknown key, missing choice_groups), or a group/option id doesn't belong to this feature."
            )
        },
    },
)
async def set_feature_choice_groups(
    feature_id: int,
    data: Annotated[
        ChoiceGroupsUpdate,
        Body(
            openapi_examples={
                "ability_score": {
                    "summary": "Choose an ability score to raise by 1",
                    "value": {
                        "choice_groups": [
                            {
                                "pick_count": 1,
                                "choice_type": "ABILITY_SCORE",
                                "options": [
                                    {"ability_effects": [{"ability": "STR", "amount": 1}]},
                                    {"ability_effects": [{"ability": "DEX", "amount": 1}]},
                                ],
                            }
                        ]
                    },
                },
                "clear": {
                    "summary": "Remove all choice groups",
                    "value": {"choice_groups": []},
                },
            },
        ),
    ],
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """
    Diff-update all choice groups for a feature. **GM only.** ``choice_groups`` is required
    (``[]`` removes every group).

    The given tree becomes the complete set, but existing rows aren't
    deleted and recreated wholesale: a group/option with an existing ``id``
    updates it in place, one with no ``id`` creates a new row, and an
    existing row whose ``id`` is missing from the payload is removed. An
    ``id`` that doesn't belong to this feature is a 422. Each option is a
    bundle — picking it applies all of its child effects together. Removing
    an option or a whole group that a character already picked clears that
    character's stored pick (it reverts to pending, see ``GET
    /characters/{id}/grants/pending``) instead of failing; every character
    currently granted the feature is re-materialized in the same
    transaction, so the removed option's effects disappear immediately for
    everyone it applied to.
    """

    return await service.set_choice_groups(feature_id, data)
