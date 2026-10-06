"""Common base of the per-capability class services (one repository, one response schema, one cache scope)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.crud.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.models.classes.class_model import Class


class ClassScopedService(BaseService[Class, ClassCreate, ClassUpdate, ClassResponse]):
    """
    Base for services that read or replace one aspect of a class.

    Writes purge ``cache_namespaces`` (override it for aspects cached elsewhere
    too) and answer with the full :class:`ClassResponse`, like ``GET /classes/{id}``.
    """

    repository: ClassRepository

    cache_namespaces: tuple[str, ...] = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with a class repository over the session."""

        super().__init__(repository=ClassRepository(db), response_schema=ClassResponse)
