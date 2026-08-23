"""User management endpoints (GM-only; role changes and deletion are found-father-only)."""

from fastapi import APIRouter, Query, status

from app.constants import UserRole
from app.core.base.service import Page
from app.core.exceptions import FoundFatherAccessException
from app.features.users.dependencies import UserServiceDep
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserResponse, UserUpdate
from app.features.users.security import CurrentUserDep, FounderDep, GmUserDep

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=Page[UserResponse])
async def get_all_users(
    user_service: UserServiceDep,
    _: GmUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
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

    return await user_service.get_all(page=page, size=size, filters={"role": role}, search=search)


@router.get("/me", response_model=UserResponse)
async def get_current_user(user_service: UserServiceDep, user: CurrentUserDep):
    """Get current user."""

    return await user_service.get_by_id(user.id)


@router.put("/me", response_model=UserResponse)
async def update_current_user(user_data: UserProfileUpdate, user_service: UserServiceDep, user: CurrentUserDep):
    """
    Update the current user's own profile (personal cabinet).

    Allows editing ``username``, ``email``, ``bio``, ``contact`` and
    ``location``. The ``role`` is never editable here — assign it through the
    GM endpoints instead.
    """

    return await user_service.update_profile(user.id, user_data)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: int, user_service: UserServiceDep, _: GmUserDep):
    """Get user by ID."""

    return await user_service.get_by_id(user_id)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, user_service: UserServiceDep, current_user: GmUserDep):
    """
    Create a new user. **GM only.**

    Assigning a non-player role (``gm`` / ``found_father``) requires the
    current user to be the found father.
    """

    if user_data.role != UserRole.PLAYER and current_user.role != UserRole.FOUND_FATHER:
        raise FoundFatherAccessException()

    return await user_service.create_user(user_data)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_data: UserUpdate, user_service: UserServiceDep, current_user: GmUserDep):
    """
    Update user by ID. **GM only.**

    Changing the ``role`` (promoting to GM or found father, or any other
    role edit) requires the current user to be the found father.
    """

    if user_data.role is not None and current_user.role != UserRole.FOUND_FATHER:
        raise FoundFatherAccessException()

    return await user_service.update_user(user_id, user_data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, user_service: UserServiceDep, current_user: FounderDep):
    """Delete user by ID. Cannot delete yourself or the default admin user. **Found-father only.**"""

    await user_service.delete_user(user_id, current_user_id=current_user.id)
    return None
