"""User repository: user-specific queries on top of :class:`BaseRepository`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models import User
from app.settings._common import utcnow


class UserRepository(BaseRepository[User]):
    """Repository for the essence of User."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db, search_fields=["username", "email"], unique_fields=["username", "email"])

    async def get_by_email(self, email: str) -> User | None:
        """Obtaining a user by email."""

        return await self.db.scalar(select(User).where(User.email == email))

    async def get_by_username(self, username: str) -> User | None:
        """Obtaining a user by username."""

        return await self.db.scalar(select(User).where(User.username == username))

    async def update_last_login(self, user: User) -> User:
        """Update user's last login timestamp."""

        user.last_login = utcnow()  # type: ignore
        await self.db.commit()
        await self.db.refresh(user)
        return user
