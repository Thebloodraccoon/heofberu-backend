"""Async DB session FastAPI dependency and its annotated alias.

``get_db`` yields one session per request; it is the canonical dependency the
HTTP test client overrides. ``DatabaseDep`` is the typed alias built on it,
imported by every feature's ``dependencies.py``. The session factory itself
(``SessionLocal``) stays stage-configured in ``app/settings``.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import settings

DatabaseDep = Annotated[AsyncSession, Depends(settings.get_db)]