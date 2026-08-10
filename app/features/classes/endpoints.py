"""Class endpoints: listing, CRUD, ability/throw/skill/progression/subclass management."""

from fastapi import APIRouter, Body, Query

from app.core.base_service import Page
from app.core.dependencies import ClassServiceDep, FounderDep, GmUserDep
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    ClassGetAllResponse,
    ClassProgressionResponse,
    ClassResponse,
    ClassUpdate,
    SavingThrowsUpdate,
    SpellSlotProgressionUpdate,
    SubclassBriefResponse,
    SubclassCreate,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate

router = APIRouter(prefix="/classes", tags=["Classes"])


@router.get(
    "",
    response_model=Page[ClassGetAllResponse],
    summary="List classes",
)
async def get_classes(
    class_service: ClassServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    search: str | None = None,
):
    """
    Return a paginated list of classes with only `id`, `name`, `hit_dice`,
    and `is_homebrew`, ordered by id.

    Open endpoint, no authentication required.

    `search` is a case-insensitive partial match against the class name.

    Response is `{items, total, page, size}` — `total` is the count of
    matching classes across every page, not just this one.

    Does not include primary abilities, saving throws, or available
    skills — use `GET /classes/{class_id}` for the full record.
    """

    return await class_service.get_all(page=page, size=size, search=search)


@router.get(
    "/{class_id}",
    response_model=ClassResponse,
    summary="Get a class by ID",
    responses={
        404: {"description": "Class with id not found."},
    },
)
async def get_class(class_id: int, class_service: ClassServiceDep):
    """
    Return a single class by ID, with full detail — including primary
    abilities, saving throws, and available skills.

    Open endpoint, no authentication required.
    """

    return await class_service.get_by_id(class_id)


@router.post(
    "",
    response_model=ClassResponse,
    status_code=201,
    summary="Create a class",
    responses={
        409: {"description": "A class with this name already exists."},
        400: {"description": "Invalid payload (skill IDs, spellcasting_ability consistency, etc.)."},
    },
)
async def create_class(
    class_service: ClassServiceDep,
    current_user: GmUserDep,
    class_data: ClassCreate = Body(
        openapi_examples={
            "fighter": {
                "summary": "Non-caster with features and a subclass",
                "value": {
                    "name": "Fighter",
                    "hit_dice": "D10",
                    "spellcasting_ability": None,
                    "primary_abilities": ["STR"],
                    "saving_throws": ["STR", "CON"],
                    "features": [
                        {"name": "Second Wind", "level": 1, "description": "Regain HP as a bonus action."},
                        {"name": "Action Surge", "level": 2, "description": "Take one additional action."},
                        {"name": "Extra Attack", "level": 5, "description": "Attack twice instead of once."},
                    ],
                    "subclasses": [
                        {
                            "name": "Champion",
                            "archetype_group_name": "Martial Archetypes",
                            "unlock_level": 3,
                            "description": "Pushes physical excellence to its limits.",
                            "features": [
                                {"name": "Improved Critics", "level": 3, "description": "Crit on 19-20."},
                                {"name": "Remarkable Athlete", "level": 7, "description": "+half prof bonus."},
                            ],
                        }
                    ],
                },
            },
            "wizard": {
                "summary": "Full caster with spell slots and a subclass",
                "value": {
                    "name": "Wizard",
                    "hit_dice": "D6",
                    "spellcasting_ability": "INT",
                    "primary_abilities": ["INT"],
                    "saving_throws": ["INT", "WIS"],
                    "available_skills": [3, 7],
                    "spell_slot_progression": [
                        {"class_level": 1, "slots": [{"spell_level": "LEVEL_1", "slots": 2}]},
                        {
                            "class_level": 3,
                            "slots": [
                                {"spell_level": "LEVEL_1", "slots": 4},
                                {"spell_level": "LEVEL_2", "slots": 2},
                            ],
                        },
                    ],
                    "subclasses": [
                        {
                            "name": "School of Evocation",
                            "archetype_group_name": "Arcane Traditions",
                            "unlock_level": 2,
                            "features": [
                                {
                                    "name": "Evocation Savant",
                                    "level": 2,
                                    "description": "Half cost to copy evocation spells.",
                                },
                                {
                                    "name": "Sculpt Spells",
                                    "level": 2,
                                    "description": "Protect allies from evocation spells.",
                                },
                            ],
                        }
                    ],
                },
            },
        }
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

    return await class_service.create_class(class_data, created_by_id=current_user.id)


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
async def update_class(class_id: int, update_data: ClassUpdate, class_service: ClassServiceDep, _: GmUserDep):
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

    return await class_service.update_class(class_id, update_data)


@router.delete(
    "/{class_id}",
    status_code=204,
    summary="Delete a class",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "Class is still in use by one or more characters."},
    },
)
async def delete_class(class_id: int, class_service: ClassServiceDep, _: FounderDep):
    """
    Delete a class. **Found-father only.**

    Also removes its primary abilities, saving throws, and links to
    available skills. Blocked if the class is still assigned to one or
    more characters.
    """

    await class_service.delete(class_id)
    return None


@router.put(
    "/{class_id}/saving-throws",
    response_model=ClassResponse,
    summary="Replace a class's saving throws",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_saving_throws(
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

    return await class_service.set_saving_throws(class_id, data)


@router.put(
    "/{class_id}/available-skills",
    response_model=ClassResponse,
    summary="Replace a class's available skills",
    responses={
        400: {"description": "One or more skill IDs don't correspond to an existing skill."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_available_skills(
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

    return await class_service.set_available_skills(class_id, data)


@router.put(
    "/{class_id}/spell-slots/{class_level}",
    response_model=ClassResponse,
    summary="Replace a class's spell slots at a given class level",
    responses={
        400: {"description": "class_level is outside the valid 1-20 range."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_spell_slots(
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

    return await class_service.set_spell_slots(class_id, class_level, data)


@router.post(
    "/{class_id}/features",
    response_model=ClassResponse,
    status_code=201,
    summary="Add a feature to a class",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def add_class_feature(
    class_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "second_wind": {
                "summary": "Add one class feature",
                "value": {
                    "name": "Second Wind",
                    "level": 1,
                    "description": "Regain HP as a bonus action.",
                },
            },
        },
    ),
):
    """
    Add one feature to a class. **GM only.**

    The feature is created with ``source_type: CLASS`` and becomes an
    auto-grant for every character of this class (level-gated) in the same
    transaction. Returns the updated class.
    """

    return await class_service.add_feature(class_id, data, created_by_id=_.id)


@router.patch(
    "/{class_id}/features/{feature_id}",
    response_model=ClassResponse,
    summary="Update one feature of a class",
    responses={
        400: {"description": "The feature belongs to a different class, or the update is invalid."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def update_class_feature(
    class_id: int,
    feature_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Improved Second Wind",
                    "level": 1,
                    "description": "Regain more HP as a bonus action.",
                },
            },
        },
    ),
):
    """
    Update one feature of a class in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is. Raising a feature's
    `level` revokes it from characters below the new level.
    """

    return await class_service.update_feature(class_id, feature_id, data)


@router.delete(
    "/{class_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a class",
    responses={
        400: {"description": "The feature belongs to a different class."},
        404: {"description": "No class exists with the given ID, or no feature exists with the given ID."},
    },
)
async def remove_class_feature(
    class_id: int,
    feature_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a class. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await class_service.remove_feature(class_id, feature_id)
    return None


@router.get(
    "/{class_id}/progression",
    response_model=ClassProgressionResponse,
    summary="Get the full 1-20 progression table",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def get_class_progression(class_id: int, class_service: ClassServiceDep):
    """
    Return the full level 1-20 progression table for a class.

    Each row contains:
    - ``level`` and ``proficiency_bonus``
    - ``spell_slots``: ``{spell_level: slots}`` (only non-zero entries)
    - ``class_features``: CLASS-source features gained at this level
    - ``subclass_features``: SUBCLASS-source features gained at this level
      (from all subclasses — useful for showing "subclass feature here")

    Open endpoint.
    """

    return await class_service.get_progression(class_id)


@router.get(
    "/{class_id}/subclasses",
    response_model=list[SubclassBriefResponse],
    summary="List subclasses for a class",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_subclasses(class_id: int, class_service: ClassServiceDep):
    """Return all subclasses for the given class. Open endpoint."""

    return await class_service.list_subclasses(class_id)


@router.get(
    "/{class_id}/subclasses/{subclass_id}",
    response_model=SubclassResponse,
    summary="Get a subclass by ID",
    responses={404: {"description": "Class or subclass not found."}},
)
async def get_subclass(class_id: int, subclass_id: int, class_service: ClassServiceDep):
    """Full subclass detail including all its features. Open endpoint."""

    return await class_service.get_subclass(class_id, subclass_id)


@router.post(
    "/{class_id}/subclasses",
    response_model=SubclassResponse,
    status_code=201,
    summary="Create a subclass",
    responses={
        404: {"description": "No class exists with the given ID."},
        409: {"description": "A subclass with this name already exists for this class."},
    },
)
async def create_subclass(
    class_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: SubclassCreate = Body(
        openapi_examples={
            "champion": {
                "summary": "Fighter — Champion subclass with features",
                "value": {
                    "name": "Champion",
                    "archetype_group_name": "Martial Archetypes",
                    "unlock_level": 3,
                    "description": "Pushes physical excellence to its limits.",
                    "features": [
                        {"name": "Improved Critical", "level": 3, "description": "Crit on 19-20."},
                        {"name": "Remarkable Athlete", "level": 7},
                        {"name": "Additional Fighting Style", "level": 10},
                        {"name": "Superior Critical", "level": 15, "description": "Crit on 18-20."},
                        {"name": "Survivor", "level": 18},
                    ],
                },
            },
        }
    ),
):
    """
    Create a subclass for the given class. **GM only.**

    ``features`` are SUBCLASS-source and are created atomically together
    with the subclass. ``unlock_level`` defaults to 3.
    """

    return await class_service.create_subclass(class_id, data, created_by_id=_.id)


@router.patch(
    "/{class_id}/subclasses/{subclass_id}",
    response_model=SubclassResponse,
    summary="Update a subclass",
    responses={404: {"description": "Class or subclass not found."}},
)
async def update_subclass(
    class_id: int, subclass_id: int, data: SubclassUpdate, class_service: ClassServiceDep, _: GmUserDep
):
    """
    Partially update a subclass's base fields. **GM only.**
    Does not touch features — manage those via the features endpoints.
    """

    return await class_service.update_subclass(class_id, subclass_id, data)


@router.post(
    "/{class_id}/subclasses/{subclass_id}/features",
    response_model=SubclassResponse,
    status_code=201,
    summary="Add a feature to a subclass",
    responses={
        404: {"description": "Class or subclass not found."},
    },
)
async def add_subclass_feature(
    class_id: int,
    subclass_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: NestedFeatureCreate = Body(
        openapi_examples={
            "improved_critical": {
                "summary": "Add one subclass feature",
                "value": {
                    "name": "Improved Critical",
                    "level": 3,
                    "description": "Your weapon attacks score a critical hit on a roll of 19 or 20.",
                },
            },
        },
    ),
):
    """
    Add one feature to a subclass. **GM only.**

    The feature is created with ``source_type: SUBCLASS`` and becomes an
    auto-grant for every character holding this subclass (level-gated) in
    the same transaction. Returns the updated subclass.
    """

    return await class_service.add_subclass_feature(class_id, subclass_id, data, created_by_id=_.id)


@router.patch(
    "/{class_id}/subclasses/{subclass_id}/features/{feature_id}",
    response_model=SubclassResponse,
    summary="Update one feature of a subclass",
    responses={
        400: {"description": "The feature belongs to a different subclass, or the update is invalid."},
        404: {"description": "Class or subclass not found, or no feature exists with the given ID."},
    },
)
async def update_subclass_feature(
    class_id: int,
    subclass_id: int,
    feature_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
    data: FeatureUpdate = Body(
        openapi_examples={
            "rename": {
                "summary": "Edit one feature",
                "value": {
                    "name": "Improved Critical (Master)",
                    "level": 3,
                    "description": "Your weapon attacks score a critical hit on a roll of 19 or 20.",
                },
            },
        },
    ),
):
    """
    Update one feature of a subclass in place. **GM only.**

    The feature keeps its id, so character grants and any player notes on
    them survive. Only `name`, `level`, `description` and `is_homebrew`
    are editable; omitted fields are left as-is. Raising a feature's
    `level` revokes it from characters below the new level.
    """

    return await class_service.update_subclass_feature(class_id, subclass_id, feature_id, data)


@router.delete(
    "/{class_id}/subclasses/{subclass_id}/features/{feature_id}",
    status_code=204,
    summary="Remove a feature from a subclass",
    responses={
        400: {"description": "The feature belongs to a different subclass."},
        404: {"description": "Class or subclass not found, or no feature exists with the given ID."},
    },
)
async def remove_subclass_feature(
    class_id: int,
    subclass_id: int,
    feature_id: int,
    class_service: ClassServiceDep,
    _: GmUserDep,
):
    """
    Remove one feature from a subclass. **GM only.**

    Deletes the feature, cascading away any `CharacterFeature` grants on
    it, and reconciles the affected characters in the same transaction.
    """

    await class_service.remove_subclass_feature(class_id, subclass_id, feature_id)
    return None


@router.delete(
    "/{class_id}/subclasses/{subclass_id}",
    status_code=204,
    summary="Delete a subclass",
    responses={404: {"description": "Class or subclass not found."}},
)
async def delete_subclass(class_id: int, subclass_id: int, class_service: ClassServiceDep, _: GmUserDep):
    """Delete a subclass and all its features. **GM only.**"""

    await class_service.delete_subclass(class_id, subclass_id)
    return None
