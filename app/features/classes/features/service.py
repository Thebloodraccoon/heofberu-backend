"""Class feature service: per-source feature CRUD, atomic with character reconciliation."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.classes.cache import invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.schemas import ClassCreate, ClassResponse, ClassUpdate
from app.features.shared.features.mixins import SourceFeatureMixin
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import NestedFeatureResponse
from app.models.class_model import Class


class ClassFeatureService(
    SourceFeatureMixin,
    BaseService[Class, ClassCreate, ClassUpdate, ClassResponse, None],
):
    """
    Everything about a class's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    come from :class:`SourceFeatureMixin`, which owns the row-level
    source-ownership rules, the source existence check (``_get_or_404``),
    and the ``_atomic()`` transaction that also runs character-grant
    reconciliation. The generic CRUD machinery comes from
    :class:`BaseService`.

    The one class-specific bit the shared engine deliberately does not do:
    a feature write also purges the ``classes`` cache namespace, because
    ``ClassFullResponse`` embeds ``features`` (see :meth:`_mutate_feature`).
    """

    repository: ClassRepository

    _feature_source_type = FeatureSourceType.CLASS

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
        )
        self._features = NestedFeatureService(db)

    async def _mutate_feature(
        self,
        source: Any,
        source_type: FeatureSourceType,
        mutate: Callable[[], Awaitable[Any]],
    ) -> NestedFeatureResponse | None:
        """
        Run the shared feature write + character reconciliation, then purge
        the ``classes`` cache namespace too.

        ``ClassFullResponse`` (``GET /classes/{id}``) embeds the class's
        ``features`` under the ``classes`` namespace, so a feature write
        must invalidate it in addition to the ``nested_features`` purge the
        shared mixin already does.
        """

        response = await super()._mutate_feature(source, source_type, mutate)
        await invalidate_class_cache()
        return response
