"""User CRUD service with password hashing and admin/self-deletion guards."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.base_service import BaseService
from app.core.security import get_password_hash
from app.features.users.exceptions import (
    DefaultUserProtectedException,
    SelfDeletionException,
    UserNotFoundException,
)
from app.features.users.repository import UserRepository
from app.features.users.schemas import UserCreate, UserProfileUpdate, UserResponse, UserUpdate
from app.models.user_model import User
from app.settings import settings


class UserService(BaseService[User, UserCreate, UserUpdate, UserResponse]):
    """
    User-specific CRUD service built on :class:`BaseService`.

    Adds behaviors the generic base class doesn't provide:
      - password hashing on create;
      - protection of the seeded default admin user from update/delete;
      - a self-deletion guard on delete;
      - lookup by email, used by the auth feature.

    (Email/username uniqueness is enforced by ``UserRepository`` via
    ``BaseRepository._check_uniqueness`` on create/update.)
    """

    repository: UserRepository

    def __init__(self, db: Session):
        super().__init__(
            repository=UserRepository(db),
            response_schema=UserResponse,
        )

    def get_user_by_email(self, email: str) -> UserResponse:
        """Return a single user by email, or raise ``UserNotFoundException``."""

        user = self.repository.get_by_email(email)
        if not user:
            raise UserNotFoundException(email=email)

        return self.response_schema.model_validate(user)

    def create_user(self, data: UserCreate) -> UserResponse:
        """
        Create a user after checking email/username aren't already taken.

        The plaintext ``password`` is hashed and stored as
        ``hashed_password`` instead of being passed straight to the
        repository, so this bypasses the generic ``super().create(...)``.
        """

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

        fields["updated_at"] = datetime.now(timezone.utc)
        updated_user = self.repository.update(user, fields)
        return self.response_schema.model_validate(updated_user)

    def update_profile(self, user_id: int, data: UserProfileUpdate) -> UserResponse:
        """
        Update a user's own profile (username, email, bio, contact, location).

        Unlike :meth:`update_user` this never touches the ``role`` and does not
        block the seeded default admin, so the admin can edit their personal
        cabinet too. Username/email uniqueness is still enforced by the
        repository.
        """

        user = self._get_or_404(user_id)
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)

        updated_user = self.repository.update(user, fields)
        return self.response_schema.model_validate(updated_user)

    def delete_user(self, user_id: int, current_user_id: int) -> bool:
        """
        Delete a user by ID.

        Raises ``RecordNotFoundError`` (mapped to a 404) if ``user_id``
        doesn't exist. Blocked for self-deletion and for the seeded default
        admin user.
        """

        user = self._get_or_404(user_id)
        if user_id == current_user_id:
            raise SelfDeletionException()

        self._ensure_not_default_user(user)
        return self.repository.delete(user)

    @staticmethod
    def _ensure_not_default_user(user: User) -> None:
        """Raise ``DefaultUserProtectedException`` if ``user`` is the seeded default admin."""

        if user.email == settings.ADMIN_LOGIN:
            raise DefaultUserProtectedException()
