from fastapi import APIRouter, status

from app.core.dependencies import ClassServiceDep, CurrentUserDep, GmUserDep
from app.features.classes.schemas import (
    AvailableSkillsUpdate,
    ClassCreate,
    ClassResponse,
    ClassUpdate,
    SavingThrowsUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[ClassResponse])
def get_classes(class_service: ClassServiceDep, _: CurrentUserDep):
    """List all classes. Any authenticated user (GM or player) can read."""
    return class_service.get_all_classes()


@router.get("/{class_id}", response_model=ClassResponse)
def get_class(class_id: int, class_service: ClassServiceDep, _: CurrentUserDep):
    """Get a single class by ID. Any authenticated user (GM or player) can read."""
    return class_service.get_class_by_id(class_id)


@router.post("/", response_model=ClassResponse, status_code=201)
def create_class(class_data: ClassCreate, class_service: ClassServiceDep, _: GmUserDep):
    """Create a new class. GM only."""
    return class_service.create_class(class_data)


@router.patch("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: int, update_data: ClassUpdate, class_service: ClassServiceDep, _: GmUserDep
):
    """Update an existing class. GM only."""
    return class_service.update_class(class_id, update_data)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(class_id: int, class_service: ClassServiceDep, _: GmUserDep):
    """Delete a class. GM only."""
    class_service.delete_class(class_id)
    return None


@router.put("/{class_id}/saving-throws", response_model=ClassResponse)
def set_class_saving_throws(
    class_id: int,
    data: SavingThrowsUpdate,
    class_service: ClassServiceDep,
    _: GmUserDep,
):
    """Fully replace the saving throw proficiencies granted by a class. GM only."""
    return class_service.set_saving_throws(class_id, data)


@router.put("/{class_id}/available-skills", response_model=ClassResponse)
def set_class_available_skills(
    class_id: int,
    data: AvailableSkillsUpdate,
    class_service: ClassServiceDep,
    _: GmUserDep,
):
    """Fully replace the skills a class may choose proficiencies from. GM only."""
    return class_service.set_available_skills(class_id, data)
