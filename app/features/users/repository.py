"""User repository: user-specific queries on top of :class:`BaseRepository`."""

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.core.base.transaction import commit_or_rollback
from app.core.exceptions import RecordAlreadyExistsError
from app.features.users.validators import normalize_email
from app.models import User
from app.settings._common import utcnow

MAX_INT4 = 2**31 - 1


class UserRepository(BaseRepository[User]):
    """User persistence: generic CRUD plus case-insensitive email lookups and last-login stamping."""

    def __init__(self, db: AsyncSession):
        """Initialise the user repository with email/username uniqueness."""

        super().__init__(User, db, search_fields=["username", "email"], unique_fields=["username", "email"])

    async def get_by_email(self, email: str) -> User | None:
        """
        Return the user with this email address, ignoring case, or ``None``.

        Compares ``lower(email)`` so accounts created before emails were
        normalized are still found; a functional index on ``lower(email)``
        (``uq_users_email_lower``) makes it an index lookup.
        """

        return await self.db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))

    async def get_by_subject(self, subject: str) -> User | None:
        """
        Resolve a JWT ``sub`` claim to a user.

        New tokens carry the immutable user id. Tokens issued before that
        change carry the email; they are still honoured so nobody is logged
        out by the deploy (they expire within the refresh lifetime).
        """

        if subject.isdecimal():
            user_id = int(subject)
            return await self.get_by_id(user_id) if user_id <= MAX_INT4 else None

        if "@" in subject:
            return await self.get_by_email(subject)

        return None

    async def update_last_login(self, user_id: int) -> None:
        """Stamp ``last_login`` with one UPDATE and commit; ``updated_at`` is left alone."""

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login=utcnow(), updated_at=User.updated_at)
            .execution_options(synchronize_session=False)
        )
        await commit_or_rollback(self.db)

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Check username exactly and email case-insensitively."""

        await super()._check_uniqueness({key: value for key, value in data.items() if key != "email"}, exclude_id)

        email = data.get("email")
        if email is None:
            return

        stmt = select(User.id).where(func.lower(User.email) == normalize_email(email))
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)

        if await self.db.scalar(stmt) is not None:
            raise RecordAlreadyExistsError(model_name="User", field="email", value=email)
