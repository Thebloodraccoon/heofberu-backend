"""User CRUD service with password hashing and admin/self-deletion guards."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.exceptions import FoundFatherAccessException
from app.core.security.password import get_password_hash_async
from app.features.users.exceptions import (
    DefaultUserProtectedException,
    SelfDeletionException,
    UserNotFoundException,
)
from app.features.users.repository import UserRepository
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserResponse, UserUpdate
from app.models import User
from app.settings import settings


class UserService(BaseService[User, UserCreate, UserUpdate, UserResponse]):
    """
    User CRUD built on :class:`BaseService`, adding password hashing on
    create, protection of the seeded default admin, and lookup by email.

    ``get_user_by_email`` is cached with a long TTL — it's the per-request
    hop ``CurrentUserDep`` takes to resolve a bearer token to a user, so
    every authenticated request would otherwise pay for a fresh DB round
    trip. Correctness comes from explicit invalidation, not the TTL: any
    write that can change what the lookup returns (role, email, username,
    deletion) calls ``_invalidate_cache()`` immediately, so a demoted/
    deleted user loses access on their very next request regardless of TTL.
    The TTL is sized to outlast a play session (a D&D session runs ~6h) so a
    long-running game doesn't keep re-fetching the same row every request;
    it's a cap on unreachable/orphaned entries, not the invalidation path.
    """

    repository: UserRepository

    cache_namespaces = ("users",)

    _USER_CACHE_TTL_SECONDS = 6 * 60 * 60

    def __init__(self, db: AsyncSession):
        """Wire up the user repository and response schema."""

        super().__init__(
            repository=UserRepository(db),
            response_schema=UserResponse,
        )

    @use_cache(ttl=_USER_CACHE_TTL_SECONDS)
    async def get_user_by_email(self, email: str) -> UserResponse:
        """Return a single user by email, or raise ``UserNotFoundException``."""

        user = await self.repository.get_by_email(email)
        if not user:
            raise UserNotFoundException(email=email)

        return self.response_schema.model_validate(user)

    async def create_user(self, data: UserCreate, current_role: UserRole) -> UserResponse:
        """
        Create a user, hashing the password before storing. Assigning a
        non-player role requires the found father.
        """

        self._ensure_role_change_allowed(data.role != UserRole.PLAYER, current_role)

        user_data = data.model_dump()
        del user_data["password"]
        user_data["hashed_password"] = await get_password_hash_async(data.password)

        user = await self.repository.create(user_data)
        return self.response_schema.model_validate(user)

    async def update_user(self, user_id: int, data: UserUpdate, current_role: UserRole) -> UserResponse:
        """
        Update a user (stamping updated_at), re-checking uniqueness. Any
        role edit requires the found father; blocked for the default admin.
        """

        self._ensure_role_change_allowed(data.role is not None, current_role)

        user = await self._get_or_404(user_id)
        self._ensure_not_default_user(user)
        fields = data.model_dump(exclude_unset=True)

        fields["updated_at"] = settings.utcnow()
        updated_user = await self.repository.update(user, fields)
        await self._invalidate_cache()

        return self.response_schema.model_validate(updated_user)

    async def update_profile(self, user_id: int, data: UserProfileUpdate) -> UserResponse:
        """
        Update a user's own profile (no role changes; not blocked for the
        default admin), stamping updated_at.
        """

        user = await self._get_or_404(user_id)
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = settings.utcnow()

        updated_user = await self.repository.update(user, fields)
        await self._invalidate_cache()

        return self.response_schema.model_validate(updated_user)

    async def delete_user(self, user_id: int, current_user_id: int) -> bool:
        """
        Delete a user (404 if missing). Blocked for self-deletion and for
        the seeded default admin.
        """

        user = await self._get_or_404(user_id)
        if user_id == current_user_id:
            raise SelfDeletionException()

        self._ensure_not_default_user(user)
        deleted = await self.repository.delete(user)
        await self._invalidate_cache()

        return deleted

    @staticmethod
    def _ensure_role_change_allowed(changes_role: bool, current_role: UserRole) -> None:
        """Raise ``FoundFatherAccessException`` unless the acting user is the found father."""

        if changes_role and current_role != UserRole.FOUND_FATHER:
            raise FoundFatherAccessException()

    @staticmethod
    def _ensure_not_default_user(user: User) -> None:
        """Raise ``DefaultUserProtectedException`` if ``user`` is the seeded default admin."""

        if user.email == settings.ADMIN_LOGIN:
            raise DefaultUserProtectedException()
