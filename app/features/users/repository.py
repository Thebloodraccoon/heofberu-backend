"""User repository: user-specific queries on top of :class:`BaseRepository`."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.base_repository import BaseRepository
from app.models import User


class UserRepository(BaseRepository[User]):
    """Repository for the essence of User."""

    def __init__(self, db: Session):
        super().__init__(User, db, search_fields=["username", "email"], unique_fields=["username", "email"])

    def get_by_email(self, email: str) -> User | None:
        """Obtaining a user by email."""
        return self.db.query(User).filter(User.email == email).first()

    def get_by_username(self, username: str) -> User | None:
        """Obtaining a user by username."""
        return self.db.query(User).filter(User.username == username).first()

    def update_last_login(self, user: User) -> User:
        """Update user's last login timestamp."""
        user.last_login = datetime.now(timezone.utc)  # type: ignore
        self.db.commit()
        self.db.refresh(user)
        return user
