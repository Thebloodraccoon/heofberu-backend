from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.core.security import get_password_hash
from app.features.users.exceptions import (
    DefaultUserProtectedException,
    SelfDeletionException,
    UserEmailAlreadyExistsException,
    UserNameAlreadyExistsException,
    UserNotFoundException,
)
from app.features.users.repository import UserRepository
from app.features.users.schemas import UserCreate, UserResponse, UserUpdate
from app.models.user_model import User
from app.settings import settings


class UserService(BaseService[User, UserCreate, UserUpdate, UserResponse]):
    """
    User-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - a uniqueness check on ``email`` and ``username`` before create/update;
      - password hashing on create;
      - protection of the seeded default admin user from update/delete;
      - a self-deletion guard on delete;
      - lookup by email, used by the auth feature.
    """

    def __init__(self, db: Session):
        super().__init__(
            repository=UserRepository(db),
            response_schema=UserResponse,
            not_found_exception_factory=lambda user_id: UserNotFoundException(user_id=user_id),
        )
        self.repository: UserRepository

    def get_user_by_id(self, user_id: int) -> UserResponse:
        """Return a single user by ID, or raise ``UserNotFoundException``."""

        return self.get_by_id(user_id)

    def get_user_by_email(self, email: str) -> UserResponse:
        """Return a single user by email, or raise ``UserNotFoundException``."""

        user = self.repository.get_by_email(email)
        if not user:
            raise UserNotFoundException(email=email)

        return self.response_schema.model_validate(user)

    def get_all_users(self, *, page: int = 0, size: int = 50) -> list[UserResponse]:
        """
        Return a page of users, serialized to ``UserResponse``.

        Args:
            page: Page number, 0-indexed.
            size: Maximum number of records to return.
        """

        return self.get_all(skip=page * size, limit=size)

    def create_user(self, data: UserCreate) -> UserResponse:
        """
        Create a user after checking email/username aren't already taken.

        The plaintext ``password`` is hashed and stored as
        ``hashed_password`` instead of being passed straight to the
        repository, so this bypasses the generic ``super().create(...)``.
        """

        self._check_email_available(data.email)
        self._check_username_available(data.username)

        user_data = data.model_dump()
        del user_data["password"]
        user_data["hashed_password"] = get_password_hash(data.password)

        user = self.repository.create(user_data)
        return self.response_schema.model_validate(user)

    def update_user(self, user_id: int, data: UserUpdate) -> UserResponse:
        """
        Update a user, re-checking email/username uniqueness if changing.

        Blocked for the seeded default admin user. Also stamps
        ``updated_at``, which the generic ``update`` doesn't do on its own.
        """

        user = self._get_or_404(user_id)
        self._ensure_not_default_user(user)
        fields = data.model_dump(exclude_unset=True)

        if "email" in fields:
            self._check_email_available(fields["email"], user_id=user_id)

        if "username" in fields:
            self._check_username_available(fields["username"], user_id=user_id)

        fields["updated_at"] = datetime.now(timezone.utc)
        updated_user = self.repository.update(user, fields)
        return self.response_schema.model_validate(updated_user)

    def delete_user(self, user_id: int, current_user_id: int) -> bool:
        """
        Delete a user by ID.

        Raises the feature's not-found exception if ``user_id`` doesn't
        exist. Blocked for self-deletion and for the seeded default admin
        user.
        """

        user = self._get_or_404(user_id)
        if user_id == current_user_id:
            raise SelfDeletionException()

        self._ensure_not_default_user(user)
        return self.repository.delete(user)

    def _check_email_available(self, email: str, user_id: int | None = None) -> None:
        """Raise ``UserEmailAlreadyExistsException`` if ``email`` is taken by another user."""

        existing_user = self.repository.get_by_email(email)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserEmailAlreadyExistsException(email)

    def _check_username_available(self, username: str, user_id: int | None = None) -> None:
        """Raise ``UserNameAlreadyExistsException`` if ``username`` is taken by another user."""

        existing_user = self.repository.get_by_username(username)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserNameAlreadyExistsException(name=username)

    @staticmethod
    def _ensure_not_default_user(user: User) -> None:
        """Raise ``DefaultUserProtectedException`` if ``user`` is the seeded default admin."""

        if user.email == settings.ADMIN_LOGIN:
            raise DefaultUserProtectedException()
