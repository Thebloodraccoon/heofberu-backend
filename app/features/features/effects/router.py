"""Feature effects endpoints: read + point writes of a feature's fixed effects and choice groups."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, status

from app.features.auth.dependencies import GmUserDep
from app.features.features.dependencies import FeatureEffectsDep
from app.features.features.effects.schemas import (
    ChoiceGroupPatch,
    ChoiceGroupPayload,
    ChoiceGroupResponse,
    ChoiceOptionPatch,
    ChoiceOptionPayload,
    EffectType,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
)

router = APIRouter()

_FORBIDDEN = {"description": "You are not a GM."}
_NOT_FOUND = {"description": "No such feature, group, option or effect (or it belongs to another parent)."}
_INVALID_PAYLOAD = {
    "description": (
        "Invalid payload (an id on a new row, duplicates, a missing/unknown skill/item/spell id, "
        "or an equal effect already exists)."
    )
}

# PATCH body of one effect: only the item fields to change.
EffectChanges = Annotated[
    dict[str, Any],
    Body(
        openapi_examples={
            "expertise": {"summary": "Skill effect: grant expertise", "value": {"grants_expertise": True}},
            "ability": {"summary": "Ability effect: change the amount", "value": {"amount": 2}},
        }
    ),
]


@router.get(
    "/{feature_id:int}/effects",
    response_model=FeatureEffectsResponse,
    summary="Read a feature's full effect tree (choice groups + fixed effects)",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature_effects(feature_id: int, service: FeatureEffectsDep):
    """Return a feature's choice groups (with their option effect bundles) and its fixed effects. Open endpoint."""

    return await service.get_effects(feature_id)


@router.post(
    "/{feature_id:int}/effects",
    response_model=FeatureEffectsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add fixed effects to a feature",
    responses={
        403: _FORBIDDEN,
        404: {"description": "No feature exists with the given ID."},
        422: _INVALID_PAYLOAD,
    },
)
async def add_feature_effects(
    feature_id: int,
    data: Annotated[
        FeatureEffectsUpdate,
        Body(
            openapi_examples={
                "add-armor": {
                    "summary": "Add medium and heavy armor proficiency",
                    "value": {
                        "static_groups": [
                            {"effect_type": "armor", "items": [{"armor_type": "MEDIUM"}, {"armor_type": "HEAVY"}]},
                        ]
                    },
                },
            },
        ),
    ],
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """
    Add fixed effects. **GM only.**

    Same ``static_groups`` shape as the read; every item is inserted as a **new**
    row (an item with an ``id`` is a 422). Returns the feature's full effect tree.
    """

    return await service.add_fixed_effects(feature_id, data)


@router.patch(
    "/{feature_id:int}/effects/{effect_type}/{effect_id:int}",
    response_model=FeatureEffectsResponse,
    summary="Change one fixed effect of a feature",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
        422: _INVALID_PAYLOAD,
    },
)
async def update_feature_effect(
    feature_id: int,
    effect_type: EffectType,
    effect_id: int,
    changes: EffectChanges,
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """
    Change fields of one fixed effect (``id`` as returned by the read). **GM only.**

    The body holds only the item fields to change (e.g. ``{"grants_expertise": true}``);
    the result must still be a valid item of that ``effect_type``. Returns the feature's full effect tree.
    """

    return await service.update_fixed_effect(feature_id, effect_type, effect_id, changes)


@router.delete(
    "/{feature_id:int}/effects/{effect_type}/{effect_id:int}",
    response_model=FeatureEffectsResponse,
    summary="Remove one fixed effect from a feature",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def remove_feature_effect(
    feature_id: int,
    effect_type: EffectType,
    effect_id: int,
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """Delete one fixed effect. **GM only.** Returns the feature's full effect tree."""

    return await service.remove_fixed_effect(feature_id, effect_type, effect_id)


@router.get(
    "/{feature_id:int}/choice-groups",
    response_model=list[ChoiceGroupResponse],
    summary="Read a feature's choice groups",
    responses={
        404: {"description": "No feature exists with the given ID."},
    },
)
async def get_feature_choice_groups(feature_id: int, service: FeatureEffectsDep):
    """Return a feature's "pick N of M" choice groups with their option effect bundles. Open endpoint."""

    return await service.get_choice_groups(feature_id)


@router.post(
    "/{feature_id:int}/choice-groups",
    response_model=list[ChoiceGroupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a choice group",
    responses={
        403: _FORBIDDEN,
        404: {"description": "No feature exists with the given ID."},
        422: _INVALID_PAYLOAD,
    },
)
async def add_feature_choice_group(
    feature_id: int,
    data: Annotated[
        ChoiceGroupPayload,
        Body(
            openapi_examples={
                "ability_score": {
                    "summary": "Choose an ability score to raise by 1",
                    "value": {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [
                            {"effects": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]},
                            {"effects": [{"effect_type": "ability", "items": [{"ability": "DEX", "amount": 1}]}]},
                        ],
                    },
                },
                "empty": {"summary": "An empty group, options added later", "value": {"choice_type": "SKILL"}},
            },
        ),
    ],
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """
    Create a choice group, optionally with its options and their effects. **GM only.**

    No ``id`` anywhere in the body. ``choice_type`` fixes the one effect type its options may
    carry and can't be changed later. Returns the feature's choice groups.
    """

    return await service.add_choice_group(feature_id, data)


@router.patch(
    "/{feature_id:int}/choice-groups/{group_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Change a choice group's pick_count / sort_order",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def update_feature_choice_group(
    feature_id: int, group_id: int, data: ChoiceGroupPatch, service: FeatureEffectsDep, _: GmUserDep
):
    """Change ``pick_count`` and/or ``sort_order`` of a group. **GM only.** Returns the feature's choice groups."""

    return await service.update_choice_group(feature_id, group_id, data)


@router.delete(
    "/{feature_id:int}/choice-groups/{group_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Delete a choice group",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def remove_feature_choice_group(feature_id: int, group_id: int, service: FeatureEffectsDep, _: GmUserDep):
    """
    Delete a group with its options. **GM only.**

    A character's pick of it is cleared (it reverts to pending, see ``GET /characters/{id}/grants/pending``).
    Returns the feature's choice groups.
    """

    return await service.remove_choice_group(feature_id, group_id)


@router.post(
    "/{feature_id:int}/choice-groups/{group_id:int}/options",
    response_model=list[ChoiceGroupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add an option to a choice group",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
        422: _INVALID_PAYLOAD,
    },
)
async def add_feature_choice_option(
    feature_id: int, group_id: int, data: ChoiceOptionPayload, service: FeatureEffectsDep, _: GmUserDep
):
    """
    Create an option (with its effect bundle ``effects``) in a group. **GM only.**

    Only the effect type the group's ``choice_type`` allows may carry items. Returns the feature's choice groups.
    """

    return await service.add_choice_option(feature_id, group_id, data)


@router.patch(
    "/{feature_id:int}/choice-groups/{group_id:int}/options/{option_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Change a choice option's sort_order",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def update_feature_choice_option(
    feature_id: int, group_id: int, option_id: int, data: ChoiceOptionPatch, service: FeatureEffectsDep, _: GmUserDep
):
    """Change an option's ``sort_order``; its effects are edited via ``.../effects``. **GM only.**"""

    return await service.update_choice_option(feature_id, group_id, option_id, data)


@router.delete(
    "/{feature_id:int}/choice-groups/{group_id:int}/options/{option_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Delete a choice option",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def remove_feature_choice_option(
    feature_id: int, group_id: int, option_id: int, service: FeatureEffectsDep, _: GmUserDep
):
    """Delete an option. **GM only.** A character's pick of it is cleared (reverts to pending)."""

    return await service.remove_choice_option(feature_id, group_id, option_id)


@router.post(
    "/{feature_id:int}/choice-groups/{group_id:int}/options/{option_id:int}/effects",
    response_model=list[ChoiceGroupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add effects to a choice option's bundle",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
        422: _INVALID_PAYLOAD,
    },
)
async def add_feature_option_effects(
    feature_id: int,
    group_id: int,
    option_id: int,
    data: FeatureEffectsUpdate,
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """Add new effect rows (same ``static_groups`` body as the fixed ones) to an option. **GM only.**"""

    return await service.add_option_effects(feature_id, group_id, option_id, data)


@router.patch(
    "/{feature_id:int}/choice-groups/{group_id:int}/options/{option_id:int}/effects/{effect_type}/{effect_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Change one effect of a choice option",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
        422: _INVALID_PAYLOAD,
    },
)
async def update_feature_option_effect(
    feature_id: int,
    group_id: int,
    option_id: int,
    effect_type: EffectType,
    effect_id: int,
    changes: EffectChanges,
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """Change fields of one effect row of an option (body: only the fields to change). **GM only.**"""

    return await service.update_option_effect(feature_id, group_id, option_id, effect_type, effect_id, changes)


@router.delete(
    "/{feature_id:int}/choice-groups/{group_id:int}/options/{option_id:int}/effects/{effect_type}/{effect_id:int}",
    response_model=list[ChoiceGroupResponse],
    summary="Remove one effect from a choice option",
    responses={
        403: _FORBIDDEN,
        404: _NOT_FOUND,
    },
)
async def remove_feature_option_effect(
    feature_id: int,
    group_id: int,
    option_id: int,
    effect_type: EffectType,
    effect_id: int,
    service: FeatureEffectsDep,
    _: GmUserDep,
):
    """Delete one effect row of an option. **GM only.**"""

    return await service.remove_option_effect(feature_id, group_id, option_id, effect_type, effect_id)
