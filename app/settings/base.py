"""Declarative base shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Typed declarative base: models declare columns as ``Mapped[...] = mapped_column(...)``."""
