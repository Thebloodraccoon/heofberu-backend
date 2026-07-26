from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.exceptions.user_exceptions import (
    DefaultUserProtectedException,
    SelfDeletionException,
    UserEmailAlreadyExistsException,
    UserNameAlreadyExistsException,
    UserNotFoundException,
)
from app.core.security import get_password_hash
from app.features.users.repository import UserRepository
from app.features.users.schemas import UserCreate, UserResponse, UserUpdate
from app.settings import settings


class UserService:
    """Business logic for the essence of User."""

    def __init__(self, db: Session):
        self.repository = UserRepository(db)

    def _check_email_exists(self, email: str, user_id: int | None = None) -> None:
        """Check if email already exists, excluding specific user ID."""
        existing_user = self.repository.get_by_email(email)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserEmailAlreadyExistsException(email)

    def _check_username_exists(self, username: str, user_id: int | None = None) -> None:
        """Check if username already exists, excluding specific user ID."""
        existing_user = self.repository.get_by_username(username)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserNameAlreadyExistsException(name=username)

    @staticmethod
    def _ensure_not_default_user(user) -> None:
        """Prevent updating or deleting the seeded default admin user."""
        if user.email == settings.ADMIN_LOGIN:
            raise DefaultUserProtectedException()

    def get_user_by_id(self, user_id: int) -> UserResponse:
        """Get user by ID with existence check."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        return UserResponse.model_validate(user)

    def get_user_by_email(self, email: str) -> UserResponse:
        """Get user by email with existence check."""
        user = self.repository.get_by_email(email)
        if not user:
            raise UserNotFoundException(email=email)
        return UserResponse.model_validate(user)

    def get_all_users(self, *, page: int = 0, size: int = 50) -> list[UserResponse]:
        """Get all users with pagination."""
        skip = page * size
        users = self.repository.get_all(skip=skip, limit=size)
        return [UserResponse.model_validate(user) for user in users]

    def create_user(self, data: UserCreate) -> UserResponse:
        """Create a new user with validation and password hashing."""
        self._check_email_exists(data.email)
        self._check_username_exists(data.username)

        user_data = data.model_dump()
        del user_data["password"]
        user_data["hashed_password"] = get_password_hash(data.password)

        user = self.repository.create(user_data)
        return UserResponse.model_validate(user)

    def update_user(self, user_id: int, data: UserUpdate) -> UserResponse:
        """Update user with validation."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)

        self._ensure_not_default_user(user)

        update_data = data.model_dump(exclude_unset=True)

        if "email" in update_data:
            self._check_email_exists(update_data["email"], user_id=user_id)

        if "username" in update_data:
            self._check_username_exists(update_data["username"], user_id=user_id)

        update_data["updated_at"] = datetime.now(timezone.utc)

        updated_user = self.repository.update(user, update_data)
        return UserResponse.model_validate(updated_user)

    def delete_user(self, user_id: int, current_user_id: int) -> bool:
        """Delete user with existence check. Cannot delete self or the default admin user."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)

        if user_id == current_user_id:
            raise SelfDeletionException()

        self._ensure_not_default_user(user)

        return self.repository.delete(user)