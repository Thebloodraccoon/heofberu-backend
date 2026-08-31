"""User management endpoints (GM-only; role changes and deletion are found-father-only)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.constants import UserRole
from app.core.base.service import Page
from app.features.users.dependencies import UserServiceDep
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserResponse, UserUpdate
from app.features.users.security import CurrentUserDep, FounderDep, GmUserDep

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=Page[UserResponse],
    summary="List users",
    responses={
        403: {"description": "Only game master has access."},
    },
)
async def get_all_users(
    user_service: UserServiceDep,
    _: GmUserDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    role: UserRole | None = Query(None, description="Filter by exact role"),
    search: str | None = Query(None, description="Case-insensitive partial match against username/email"),
):
    """
    Get all users with pagination. **GM only.**

    `role` is an exact match. `search` is a case-insensitive partial
    match against username or email, and can be combined with `role`.

    Response is `{items, total, page, size}` — `total` is the count of
    matching users across every page, not just this one.
    """

    return await user_service.get_all(page=page, size=size, filters={"role": role}, search=search)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current user",
    responses={
        401: {"description": "Access token missing, malformed, expired, blacklisted, or of the wrong type."},
        404: {"description": "The user behind the token no longer exists."},
    },
)
async def get_current_user(user_service: UserServiceDep, user: CurrentUserDep):
    """
    Return the authenticated user's own profile.

    Any authenticated user — resolves the caller from the bearer token
    and returns their full ``UserResponse``.
    """

    return await user_service.get_by_id(user.id)


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update the current user's profile",
    responses={
        400: {"description": "Invalid email, or username/email already taken by another account."},
        401: {"description": "Access token missing, malformed, expired, blacklisted, or of the wrong type."},
        404: {"description": "The user behind the token no longer exists."},
        422: {"description": "Validation error — payload empty, unknown fields present, or field rules violated."},
    },
)
async def update_current_user(data: UserProfileUpdate, user_service: UserServiceDep, user: CurrentUserDep):
    """
    Update the current user's own profile (personal cabinet).

    Allows editing ``username``, ``email``, ``bio``, ``phone``, ``discord``
    and ``telegram``. The ``role`` is never editable here — assign it through the
    GM endpoints instead.
    """

    return await user_service.update_profile(user.id, data)


@router.get(
    "/{user_id:int}",
    response_model=UserResponse,
    summary="Get a user by ID",
    responses={
        403: {"description": "Only game master has access."},
        404: {"description": "No user exists with the given ID."},
    },
)
async def get_user_by_id(user_id: int, user_service: UserServiceDep, _: GmUserDep):
    """
    Get user by ID. **GM only.**

    Returns the full ``UserResponse`` for any account, regardless of role.
    """

    return await user_service.get_by_id(user_id)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    responses={
        400: {"description": "Username/email already taken, invalid email, or weak password."},
        403: {"description": "Assigning a non-player role requires the found father."},
        422: {"description": "Validation error — username length/charset, password length, or body shape is invalid."},
    },
)
async def create_user(
    data: Annotated[
        UserCreate,
        Body(
            openapi_examples={
                "player": {
                    "summary": "New player account",
                    "value": {
                        "username": "aria_of_the_vale",
                        "email": "aria@example.com",
                        "password": "correct-horse-battery",
                        "role": "player",
                        "bio": "Ranger from the northern vale.",
                    },
                },
                "gm": {
                    "summary": "New GM account — founder only",
                    "value": {
                        "username": "table_gm",
                        "email": "gm@table.example.com",
                        "password": "behind-the-screen",
                        "role": "gm",
                    },
                },
            },
        ),
    ],
    user_service: UserServiceDep,
    current_user: GmUserDep,
):
    """
    Create a new user. **GM only.**

    Assigning a non-player role (``gm`` / ``found_father``) requires the
    current user to be the found father.
    """

    return await user_service.create_user(data, current_role=current_user.role)


@router.put(
    "/{user_id:int}",
    response_model=UserResponse,
    summary="Update a user",
    responses={
        400: {"description": "Username/email already taken, invalid email, or default admin protection applies."},
        403: {"description": "Changing a role requires the found father; updating the default admin is forbidden."},
        404: {"description": "No user exists with the given ID."},
        422: {"description": "Validation error — payload empty or field rules violated."},
    },
)
async def update_user(
    user_id: int,
    data: Annotated[
        UserUpdate,
        Body(
            openapi_examples={
                "profile_edit": {
                    "summary": "Edit profile fields",
                    "value": {
                        "bio": "Promoted to lorekeeper of the guild.",
                        "discord": "guild_keeper",
                    },
                },
                "role_change": {
                    "summary": "Promote to GM — founder only",
                    "value": {
                        "role": "gm",
                    },
                },
            },
        ),
    ],
    user_service: UserServiceDep,
    current_user: GmUserDep,
):
    """
    Update user by ID. **GM only.**

    Changing the ``role`` (promoting to GM or found father, or any other
    role edit) requires the current user to be the found father.
    """

    return await user_service.update_user(user_id, data, current_role=current_user.role)


@router.delete(
    "/{user_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user",
    responses={
        403: {"description": "Found-father only; cannot delete yourself or the seeded default admin."},
        404: {"description": "No user exists with the given ID."},
    },
)
async def delete_user(user_id: int, user_service: UserServiceDep, current_user: FounderDep):
    """
    Delete user by ID. Founder only.

    Cannot delete yourself or the seeded default admin user — both raise
    a 403 via ``SelfDeletionException`` /
    ``DefaultUserProtectedException``.
    """

    await user_service.delete_user(user_id, current_user_id=current_user.id)
    return None
