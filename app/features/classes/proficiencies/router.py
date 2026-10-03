"""Class proficiency endpoints: full replacement of saving throws, armor and weapon proficiencies."""

from typing import Annotated, Any

from fastapi import APIRouter, Body

from app.features.auth.dependencies import GmUserDep
from app.features.classes.crud.schemas import ClassResponse
from app.features.classes.dependencies import ClassProficienciesDep
from app.features.classes.proficiencies.schemas import (
    ArmorProficienciesUpdate,
    SavingThrowsUpdate,
    WeaponProficienciesUpdate,
)

router = APIRouter()


def _add_replace_route(
    *,
    path: str,
    method_name: str,
    schema: type,
    summary: str,
    what: str,
    removed: str,
    examples: dict[str, Any],
) -> None:
    """Register ``PUT {path}`` calling ``ClassProficiencyService.<method_name>`` with the validated body."""

    async def endpoint(
        class_id: int,
        data: Annotated[schema, Body(openapi_examples=examples)],  # type: ignore[valid-type]  # route factory
        class_service: ClassProficienciesDep,
        _: GmUserDep,
    ):
        return await getattr(class_service, method_name)(class_id, data)

    endpoint.__name__ = method_name
    endpoint.__doc__ = (
        f"Replace all {what} for a class. **GM only.**\n\nFull replace: any {removed} not included is removed."
    )

    router.add_api_route(
        path,
        endpoint,
        methods=["PUT"],
        response_model=ClassResponse,
        summary=summary,
        responses={404: {"description": "No class exists with the given ID."}},
    )


_add_replace_route(
    path="/{class_id:int}/saving-throws",
    method_name="set_saving_throws",
    schema=SavingThrowsUpdate,
    summary="Replace a class's saving throws",
    what="saving throw proficiencies",
    removed="throw",
    examples={
        "replace": {"summary": "Replace with two saving throws", "value": {"saving_throws": ["STR", "CON"]}},
        "clear": {"summary": "Clear all saving throws", "value": {"saving_throws": []}},
    },
)

_add_replace_route(
    path="/{class_id:int}/armor-proficiencies",
    method_name="set_armor_proficiencies",
    schema=ArmorProficienciesUpdate,
    summary="Replace a class's armor proficiencies",
    what="armor proficiencies",
    removed="armor type",
    examples={
        "fighter": {
            "summary": "Fighter — all armor + shields",
            "value": {"armor_proficiencies": ["LIGHT", "MEDIUM", "HEAVY", "SHIELD"]},
        },
        "clear": {"summary": "Clear all armor proficiencies", "value": {"armor_proficiencies": []}},
    },
)

_add_replace_route(
    path="/{class_id:int}/weapon-proficiencies",
    method_name="set_weapon_proficiencies",
    schema=WeaponProficienciesUpdate,
    summary="Replace a class's weapon proficiencies",
    what="weapon proficiencies",
    removed="weapon category",
    examples={
        "fighter": {
            "summary": "Fighter — simple + martial weapons",
            "value": {"weapon_proficiencies": ["SIMPLE", "MARTIAL"]},
        },
        "wizard": {"summary": "Wizard — simple weapons only", "value": {"weapon_proficiencies": ["SIMPLE"]}},
        "clear": {"summary": "Clear all weapon proficiencies", "value": {"weapon_proficiencies": []}},
    },
)
