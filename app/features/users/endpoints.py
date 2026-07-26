from fastapi import APIRouter, Query, status

from app.core.dependencies import GmUserDep, UserServiceDep
from app.features.users.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter()


@router.get("/", response_model=list[UserResponse])
def get_all_users(
    user_service: UserServiceDep,
    _: GmUserDep,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
):
    """Get all users with pagination."""
    return user_service.get_all_users(page=page, size=size)


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(user_id: int, user_service: UserServiceDep, _: GmUserDep):
    """Get user by ID."""
    return user_service.get_user_by_id(user_id)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_data: UserCreate, user_service: UserServiceDep, _: GmUserDep):
    """Create a new user."""
    return user_service.create_user(user_data)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, user_service: UserServiceDep, _: GmUserDep):
    """Update user by ID."""
    return user_service.update_user(user_id, user_data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, user_service: UserServiceDep, current_user: GmUserDep):
    """Delete user by ID. Cannot delete yourself or the default admin user."""
    user_service.delete_user(user_id, current_user_id=current_user.id)
    return None
