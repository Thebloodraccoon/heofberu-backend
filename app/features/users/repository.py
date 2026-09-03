"""User repository: user-specific queries on top of :class:`BaseRepository`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models import User
from app.settings._common import utcnow


class UserRepository(BaseRepository[User]):
    """User persistence: generic CRUD plus email/username lookups and last-login stamping."""

    def __init__(self, db: AsyncSession):
        """Initialise the user repository with email/username uniqueness."""

        super().__init__(User, db, search_fields=["username", "email"], unique_fields=["username", "email"])

    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this exact email address, or ``None``."""

        return await self.db.scalar(select(User).where(User.email == email))

    async def get_by_username(self, username: str) -> User | None:
        """Return the user with this exact username, or ``None``."""

        return await self.db.scalar(select(User).where(User.username == username))

    async def update_last_login(self, user: User) -> User:
        """Stamp ``user.last_login`` with the current UTC time, commit, and return the refreshed user."""

        user.last_login = utcnow()  # type: ignore
        await self.commit_or_flush()
        await self.db.refresh(user)
        return user
