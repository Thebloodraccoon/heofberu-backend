from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.utils.pwd_utils import get_password_hash
from app.exceptions.user_exceptions import (
    UserEmailAlreadyExistsException,
    UserNameAlreadyExistsException,
    UserNotFoundException,
)
from app.users.repository import UserRepository
from app.users.schemas import UserCreate, UserResponse, UserUpdate


class UserService:
    """Business logic for the essence of User."""

    def __init__(self, db: Session):
        self.repository = UserRepository(db)

    def check_email_exists(self, email: str, user_id: int | None = None) -> None:  # type: ignore
        """Check if email already exists, excluding specific user ID."""
        existing_user = self.repository.get_by_email(email)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserEmailAlreadyExistsException(email)

    def check_username_exists(self, username: str, user_id: int | None = None) -> None:  # type: ignore
        """Check if username already exists, excluding specific user ID."""
        existing_user = self.repository.get_by_username(username)
        if existing_user and (user_id is None or existing_user.id != user_id):
            raise UserNameAlreadyExistsException(name=username)

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
        self.check_email_exists(data.email)
        self.check_username_exists(data.username)

        user_data = data.model_dump()
        del user_data["password"]
        user_data["hashed_password"] = get_password_hash(data.password)

        user = self.repository.create(user_data)
        return UserResponse.model_validate(user)

    def update_user(self, user_id: int, data: UserUpdate) -> UserResponse:
        """Update user with validation and optional password hashing."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)

        update_data = data.model_dump(exclude_unset=True)

        if "email" in update_data:
            self.check_email_exists(update_data["email"], user_id=user_id)

        if "username" in update_data:
            self.check_username_exists(update_data["username"], user_id=user_id)

        update_data["updated_at"] = datetime.now()

        updated_user = self.repository.update(user, update_data)
        return UserResponse.model_validate(updated_user)

    def delete_user(self, user_id: int) -> bool:
        """Delete user with existence check."""
        user = self.repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(user_id=user_id)
        return self.repository.delete(user)
