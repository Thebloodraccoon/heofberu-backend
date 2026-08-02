from fastapi import APIRouter, Query, status

from app.constants import UserRole
from app.core.dependencies import GmUserDep, UserServiceDep
from app.features.users.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserResponse])
def get_all_users(
    user_service: UserServiceDep,
    _: GmUserDep,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    role: UserRole | None = Query(None, description="Filter by exact role"),
    search: str | None = Query(None, description="Case-insensitive partial match against username/email"),
):
    """
    Get all users with pagination.

    `role` is an exact match. `search` is a case-insensitive partial
    match against username or email, and can be combined with `role`.

    Response is `{items, total, page, size}` — `total` is the count of
    matching users across every page, not just this one.
    """
    return user_service.get_all(page=page, size=size, filters={"role": role}, search=search)


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(user_id: int, user_service: UserServiceDep, _: GmUserDep):
    """Get user by ID."""
    return user_service.get_by_id(user_id)


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
