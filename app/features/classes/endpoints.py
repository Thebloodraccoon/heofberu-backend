from fastapi import APIRouter, Body

from app.core.dependencies import ClassServiceDep, GmUserDep
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassBriefResponse,
    ClassCreate,
    ClassResponse,
    ClassUpdate,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
)

router = APIRouter(prefix="/classes", tags=["Classes"])


@router.get(
    "/",
    response_model=list[ClassResponse],
    summary="List classes (full detail)",
)
def get_classes(class_service: ClassServiceDep, skip: int = 0, limit: int = 10):
    """
    Return a paginated list of classes, ordered by name, each with full
    detail — including primary abilities, saving throws, and available
    skills.

    Open endpoint, no authentication required.

    For a lighter payload (no abilities/throws/skills), use
    `GET /classes/brief` instead.
    """
    return class_service.get_all(skip=skip, limit=limit)


@router.get(
    "/brief",
    response_model=list[ClassBriefResponse],
    summary="List classes (minimal fields)",
)
def get_classes_brief(class_service: ClassServiceDep, skip: int = 0, limit: int = 10):
    """
    Return a paginated list of classes with only `id`, `name`, `hit_dice`,
    and `is_homebrew`.

    Open endpoint, no authentication required.

    Does not include primary abilities, saving throws, or available
    skills — use `GET /classes/{class_id}` for the full record. Intended
    for dropdowns, tables, and similar listing UI where the full payload
    is unnecessary.
    """
    return class_service.list_brief(skip=skip, limit=limit)


@router.get(
    "/{class_id}",
    response_model=ClassResponse,
    summary="Get a class by ID",
    responses={
        404: {"description": "Class with id not found."},
    },
)
def get_class(class_id: int, class_service: ClassServiceDep):
    """
    Return a single class by ID, with full detail — including primary
    abilities, saving throws, and available skills.

    Open endpoint, no authentication required.
    """
    return class_service.get_by_id(class_id)


@router.post(
    "/",
    response_model=ClassResponse,
    status_code=201,
    summary="Create a class",
    responses={
        409: {"description": "A class with this name already exists."},
        400: {
            "description": (
                "One or more `available_skills` IDs don't correspond to an existing skill, "
                "or `spellcasting_ability` was set but is not included in `primary_abilities`."
            )
        },
    },
)
def create_class(
    class_service: ClassServiceDep,
    current_user: GmUserDep,
    class_data: ClassCreate = Body(
        openapi_examples={
            "non_caster": {
                "summary": "Non-caster — spellcasting_ability explicitly null",
                "value": {
                    "name": "Fighter",
                    "hit_dice": "D10",
                    "spellcasting_ability": None,
                    "primary_abilities": ["STR"],
                    "saving_throws": ["STR", "CON"],
                },
            },
            "caster_with_skills": {
                "summary": "Caster, with primary abilities, saving throws, and available skills",
                "value": {
                    "name": "Wizard",
                    "hit_dice": "D6",
                    "skill_choice_count": 2,
                    "description": "A scholarly magic-user.",
                    "spellcasting_ability": "INT",
                    "primary_abilities": ["INT"],
                    "saving_throws": ["INT", "WIS"],
                    "available_skills": [3, 7],
                },
            },
        },
    ),
):
    """
    Create a new class. **GM only.**

    `spellcasting_ability` must always be supplied explicitly — pass
    `null` for a non-caster class. If non-null, it must also appear in
    `primary_abilities`.

    `primary_abilities`, `saving_throws`, and `available_skills` are
    optional. If provided, they're saved together with the class in a
    single transaction — the class is fully set up in one call instead of
    a `POST` followed by separate `PUT` calls.
    """
    return class_service.create_class(class_data, created_by_id=current_user.id)


@router.patch(
    "/{class_id}",
    response_model=ClassResponse,
    summary="Update a class's fields",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "Another class already uses the requested name."},
        400: {
            "description": (
                "spellcasting_ability was set but is not included in primary_abilities, or "
                "primary_abilities was updated without spellcasting_ability and no longer "
                "includes the class's current spellcasting_ability."
            )
        },
    },
)
def update_class(class_id: int, update_data: ClassUpdate, class_service: ClassServiceDep, _: GmUserDep):
    """
    Partially update a class. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. `primary_abilities` and `saving_throws`, when
    included, are fully replaced (not merged) — the same semantics as the
    dedicated `PUT /classes/{class_id}/saving-throws` endpoint. Does not
    touch available skills — use `PUT /classes/{class_id}/available-skills`
    for that.

    If `primary_abilities` is changed without also passing
    `spellcasting_ability`, the class's current `spellcasting_ability`
    must still be present in the new `primary_abilities` list — otherwise
    the request is rejected. Pass `spellcasting_ability` explicitly in the
    same request to change it alongside `primary_abilities`.
    """
    return class_service.update_class(class_id, update_data)


@router.delete(
    "/{class_id}",
    status_code=204,
    summary="Delete a class",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "Class is still in use by one or more characters."},
    },
)
def delete_class(class_id: int, class_service: ClassServiceDep, _: GmUserDep):
    """
    Delete a class. **GM only.**

    Also removes its primary abilities, saving throws, and links to
    available skills. Blocked if the class is still assigned to one or
    more characters.
    """
    class_service.delete_class(class_id)
    return None


@router.put(
    "/{class_id}/saving-throws",
    response_model=ClassResponse,
    summary="Replace a class's saving throws",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
def set_class_saving_throws(
    class_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: SavingThrowsUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two saving throws",
                "value": {"saving_throws": ["STR", "CON"]},
            },
            "clear": {
                "summary": "Clear all saving throws",
                "value": {"saving_throws": []},
            },
        },
    ),
):
    """
    Replace all saving throw proficiencies for a class. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of saving throws for this class — any throw not included
    is removed. Send an empty list to clear all saving throws.
    """
    return class_service.set_saving_throws(class_id, data)


@router.put(
    "/{class_id}/available-skills",
    response_model=ClassResponse,
    summary="Replace a class's available skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No class exists with the given ID."},
    },
)
def set_class_available_skills(
    class_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: AvailableSkillsUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Replace with two skills",
                "value": {"skill_ids": [3, 7]},
            },
            "clear": {
                "summary": "Clear all available skills",
                "value": {"skill_ids": []},
            },
        },
    ),
):
    """
    Replace all skills a class may choose proficiencies from. **GM only.**

    Full replace, not merge: the `skill_ids` in the request body become
    the complete set of skills this class offers — any skill not included
    is removed. Send an empty list to clear all available skills.
    """
    return class_service.set_available_skills(class_id, data)


@router.put(
    "/{class_id}/spell-slots/{class_level}",
    response_model=ClassResponse,
    summary="Replace a class's spell slots at a given class level",
    responses={
        400: {"description": "class_level is outside the valid 1-20 range."},
        404: {"description": "No class exists with the given ID."},
    },
)
def set_class_spell_slots(
    class_id: int,
    class_level: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: SpellSlotProgressionUpdate = Body(
        openapi_examples={
            "level_5_wizard": {
                "summary": "Level 5 Wizard — 3 first-level, 3 second-level, 2 third-level slots",
                "value": {
                    "slots": [
                        {"spell_level": "LEVEL_1", "slots": 3},
                        {"spell_level": "LEVEL_2", "slots": 3},
                        {"spell_level": "LEVEL_3", "slots": 2},
                    ]
                },
            },
            "clear": {
                "summary": "Clear all slots at this class level",
                "value": {"slots": []},
            },
        },
    ),
):
    """
    Replace the spell slots a class grants at a single `class_level`.
    **GM only.**

    Full replace, not merge, scoped to this `class_level`: the
    `spell_level`/`slots` pairs in the request body become the complete
    set of slots granted at this level — any `spell_level` not included
    is reset to 0. Other class levels are untouched; call this endpoint
    once per level to build up the full progression table.

    No check is made that the class has a `spellcasting_ability` —
    progressions can be set on any class, including to support
    multiclass-style slot tables.
    """
    return class_service.set_spell_slots(class_id, class_level, data)
