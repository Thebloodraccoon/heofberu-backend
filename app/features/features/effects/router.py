"""Feature effects endpoints: read + full-replace of a feature's fixed effects and choice groups (Phase 3)."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.features.dependencies import FeatureEffectsDep
from app.features.features.effects.schemas import (
    ChoiceGroupResponse,
    ChoiceGroupsUpdate,
    FeatureEffectsResponse,
    FeatureEffectsUpdate,
)
from app.features.users.security import GmUserDep

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
    summary="Replace a feature's fixed (automatic) effects",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No feature exists with the given ID."},
        422: {"description": "Invalid effect payload."},
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
    Replace all fixed effects for a feature. **GM only.**

    Full replace (not merge): each list becomes the complete set of that
    effect type; send ``[]`` to clear it. Effects apply automatically to
    every character the feature is granted to (existing characters are
    re-materialized in the same transaction). Choice groups are managed via
    ``PUT /features/{id}/choice-groups``.
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
    summary="Replace a feature's choice groups",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No feature exists with the given ID."},
        422: {"description": "Invalid choice-group payload."},
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
                                "label": "Choose an ability",
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
    Replace all choice groups for a feature. **GM only.**

    Full replace: the given tree becomes the complete set. Each option is a
    bundle — picking it applies all of its child effects together. Grants
    whose picks referenced removed options have those picks re-materialized
    by the sync on the next progression write.
    """

    return await service.set_choice_groups(feature_id, data)
