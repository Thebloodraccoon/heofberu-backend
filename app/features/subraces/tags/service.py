"""Subrace tags service: full replacement and id resolution."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.shared.catalog.cache import CatalogCacheMixin
from app.features.shared.tags.mixins import TagsManagerMixin
from app.features.subraces.cache import SUBRACE_CACHE_NAMESPACES
from app.features.subraces.crud.schemas import SubraceCreate, SubraceResponse, SubraceUpdate
from app.features.subraces.tags.repository import SubraceTagsRepository
from app.models.races.subrace_model import Subrace


class SubraceTagService(
    TagsManagerMixin,
    CatalogCacheMixin,
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """Full replacement and id-resolution for subrace tags."""

    repository: SubraceTagsRepository

    # Tag listings carry a per-tag usage count, so they change with every assignment.
    cache_namespaces = (*SUBRACE_CACHE_NAMESPACES, "tags")

    def __init__(self, db: AsyncSession):
        """Initialize with a subrace tags repository and the subrace response schema."""

        super().__init__(
            repository=SubraceTagsRepository(db),
            response_schema=SubraceResponse,
        )
