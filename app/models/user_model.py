from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.constants import USER_ROLES, create_enum_constraint
from app.settings import settings


class User(settings.Base):  # type: ignore
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)

    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="player")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login = Column(DateTime)

    characters = relationship(
        "Character",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            create_enum_constraint("role", USER_ROLES, nullable=False),
            name="check_user_role",
        ),
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
