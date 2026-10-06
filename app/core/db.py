"""
Annotated alias of the async DB session dependency.

``DatabaseDep`` wraps ``settings.get_db`` (one ``AsyncSession`` per request, built
in ``app/settings``) and is imported by every feature's ``dependencies.py``.
``settings.get_db`` is the dependency the HTTP test client overrides.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import settings

DatabaseDep = Annotated[AsyncSession, Depends(settings.get_db)]
