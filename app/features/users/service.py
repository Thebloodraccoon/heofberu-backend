"""User CRUD service with password hashing, role/ownership guards and the per-request auth user lookup."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.base.service import BaseService
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import build_cache_key, use_cache
from app.core.cache.namespaces import dependents
from app.core.exceptions import FoundFatherAccessException
from app.core.security.password import get_password_hash_async
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES
from app.features.users.exceptions import (
    DefaultUserProtectedException,
    SelfDeletionException,
    UserNotFoundException,
)
from app.features.users.repository import MAX_INT4, UserRepository
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserResponse, UserUpdate
from app.features.users.validators import normalize_email
from app.models import User
from app.settings import settings

USERS_CACHE_NAMESPACE = "users"


def user_cache_key(user_id: int) -> str:
    """Exact cache key of ``UserService.get_auth_user(user_id)``, for point invalidation."""

    return build_cache_key(UserService.get_auth_user, None, user_id, namespace=USERS_CACHE_NAMESPACE)


async def invalidate_user_cache(db: AsyncSession, user_id: int, *, username_changed: bool = False) -> None:
    """
    Drop one user's cached auth record once the surrounding transaction has committed.

    ``username_changed`` also purges the payloads that embed the username (articles' ``author``).
    """

    namespaces = dependents("users") if username_changed else ()
    await invalidate_after_commit(db, *namespaces, keys=[user_cache_key(user_id)])


class UserService(BaseService[User, UserCreate, UserUpdate, UserResponse]):
    """
    User CRUD built on :class:`BaseService`, adding password hashing on
    create, role-based edit guards, protection of the seeded default admin
    and the cached lookup that resolves a bearer token to a user.

    ``get_auth_user`` is the per-request hop ``CurrentUserDep`` takes, so it
    is cached by user id. Correctness comes from point invalidation after
    every write that touches the user (role, profile, deletion, last login);
    the short TTL only bounds the damage if an invalidation is lost to a
    Redis outage, which would otherwise leave a demoted user with their old
    role.
    """

    repository: UserRepository

    cache_namespaces = (USERS_CACHE_NAMESPACE,)

    _USER_CACHE_TTL_SECONDS = 5 * 60

    def __init__(self, db: AsyncSession):
        """Wire up the user repository and response schema."""

        super().__init__(
            repository=UserRepository(db),
            response_schema=UserResponse,
        )

    @use_cache(ttl=_USER_CACHE_TTL_SECONDS)
    async def get_auth_user(self, user_id: int) -> UserResponse:
        """Return the user with this id, or raise ``UserNotFoundException``."""

        user = await self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()

        return self.response_schema.model_validate(user)

    async def resolve_subject_id(self, subject: str) -> int:
        """
        Turn a token ``sub`` claim into a user id.

        Id subjects need no database access; legacy email subjects cost one lookup.
        """

        if subject.isdecimal():
            user_id = int(subject)
            if user_id > MAX_INT4:
                raise UserNotFoundException()
            return user_id

        user = await self.repository.get_by_subject(subject)
        if not user:
            raise UserNotFoundException()

        return user.id

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
        Update a user (stamping updated_at), re-checking uniqueness.

        Any role edit requires the found father, and only the found father
        may edit non-player accounts (a GM able to change a GM's or the
        founder's email could take the account over through password reset).
        Blocked for the default admin.
        """

        self._ensure_role_change_allowed(data.role is not None, current_role)

        user = await self._get_or_404(user_id)
        self._ensure_not_default_user(user)
        self._ensure_can_edit(user, current_role)

        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = settings.utcnow()

        updated_user = await self.repository.update(user, fields)
        await invalidate_user_cache(self.repository.db, user_id, username_changed="username" in fields)

        return self.response_schema.model_validate(updated_user)

    async def update_profile(self, user_id: int, data: UserProfileUpdate) -> UserResponse:
        """
        Update a user's own profile (no role changes), stamping updated_at.

        The default admin may edit their profile but not their email: the
        protection is keyed by that email, so changing it would lift it.
        """

        user = await self._get_or_404(user_id)
        fields = data.model_dump(exclude_unset=True)

        if (
            self._is_default_user(user)
            and "email" in fields
            and normalize_email(fields["email"]) != normalize_email(user.email)
        ):
            raise DefaultUserProtectedException("The default admin's email cannot be changed.")

        fields["updated_at"] = settings.utcnow()

        updated_user = await self.repository.update(user, fields)
        await invalidate_user_cache(self.repository.db, user_id, username_changed="username" in fields)

        return self.response_schema.model_validate(updated_user)

    async def delete_user(self, user_id: int, current_user_id: int) -> bool:
        """
        Delete a user (404 if missing). Blocked for self-deletion and for
        the seeded default admin. Cached articles carry ``author_id`` (nulled by the
        delete), so they are purged along with the user's auth record.
        """

        user = await self._get_or_404(user_id)
        if user_id == current_user_id:
            raise SelfDeletionException()

        self._ensure_not_default_user(user)
        deleted = await self.repository.delete(user)
        await invalidate_after_commit(self.repository.db, *ARTICLE_CACHE_NAMESPACES, keys=[user_cache_key(user_id)])

        return deleted

    @staticmethod
    def _ensure_role_change_allowed(changes_role: bool, current_role: UserRole) -> None:
        """Raise ``FoundFatherAccessException`` unless the acting user is the found father."""

        if changes_role and current_role != UserRole.FOUND_FATHER:
            raise FoundFatherAccessException()

    @staticmethod
    def _ensure_can_edit(target: User, current_role: UserRole) -> None:
        """Raise ``FoundFatherAccessException`` when a non-founder edits a non-player account."""

        if current_role != UserRole.FOUND_FATHER and target.role != UserRole.PLAYER:
            raise FoundFatherAccessException()

    @staticmethod
    def _is_default_user(user: User) -> bool:
        """Whether ``user`` is the seeded default admin (identified by the configured login email)."""

        return normalize_email(user.email) == normalize_email(settings.ADMIN_LOGIN)

    @classmethod
    def _ensure_not_default_user(cls, user: User) -> None:
        """Raise ``DefaultUserProtectedException`` if ``user`` is the seeded default admin."""

        if cls._is_default_user(user):
            raise DefaultUserProtectedException()
