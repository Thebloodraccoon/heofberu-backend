"""ORM model for registered users."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import UserRole
from app.models.enums import UserRoleType
from app.settings._common import utcnow
from app.settings.base import Base

if TYPE_CHECKING:
    from app.models.character.character_model import Character


class User(Base):
    """A registered user account (GM or player), owning characters."""

    __tablename__ = "users"
    # ``role`` is a VARCHAR (see ``UserRoleType``); the DB still refuses unknown roles since it gates permissions.
    __table_args__ = (
        CheckConstraint("role IN ('GM', 'PLAYER', 'FOUND_FATHER')", name="ck_users_role"),
        # Emails are stored normalized (stripped, lowercase) and looked up by ``lower(email)``; the unique functional
        # index serves that lookup and refuses ``A@x.com`` next to ``a@x.com`` even under a registration race.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str] = mapped_column()

    hashed_password: Mapped[str] = mapped_column()
    role: Mapped[UserRole] = mapped_column(UserRoleType, default=UserRole.PLAYER, server_default="PLAYER")

    bio: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(length=100))
    discord: Mapped[str | None] = mapped_column(String(length=100))
    telegram: Mapped[str | None] = mapped_column(String(length=100))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)

    characters: Mapped[list[Character]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
