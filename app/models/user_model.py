"""ORM model for registered users."""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.constants import UserRole
from app.models.enums import UserRoleType
from app.settings import settings
from app.settings._common import utcnow


class User(settings.Base):  # type: ignore
    """A registered user account (GM or player), owning characters."""

    __tablename__ = "users"
    # ``role`` is a VARCHAR (see ``UserRoleType``); the DB still refuses unknown roles since it gates permissions.
    __table_args__ = (CheckConstraint("role IN ('GM', 'PLAYER', 'FOUND_FATHER')", name="ck_users_role"),)

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)

    hashed_password = Column(String, nullable=False)
    role = Column(UserRoleType, nullable=False, default=UserRole.PLAYER, server_default="PLAYER")

    bio = Column(Text, nullable=True)
    phone = Column(String(length=100), nullable=True)
    discord = Column(String(length=100), nullable=True)
    telegram = Column(String(length=100), nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )
    last_login = Column(DateTime)

    characters = relationship(
        "Character",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
