"""Background feature service: per-source feature CRUD, atomic with character reconciliation."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.backgrounds.cache import invalidate_background_cache
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.shared.features.mixins import SourceFeatureMixin
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import NestedFeatureResponse
from app.models.background_model import Background


class BackgroundFeatureService(
    SourceFeatureMixin,
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None],
):
    """
    Everything about a background's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    come from :class:`SourceFeatureMixin`, which owns the row-level
    source-ownership rules, the source existence check (``_get_or_404``),
    and the ``_atomic()`` transaction that also runs character-grant
    reconciliation. The generic CRUD machinery comes from
    :class:`BaseService`.

    The one background-specific bit the shared engine deliberately does
    not do: a feature write also purges the ``backgrounds`` cache
    namespace, because ``BackgroundFullResponse`` embeds ``features``
    (see :meth:`_mutate_feature`).
    """

    repository: BackgroundRepository

    _feature_source_type = FeatureSourceType.BACKGROUND

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
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
        the ``backgrounds`` cache namespace too.

        ``BackgroundFullResponse`` (``GET /backgrounds/{id}``) embeds the
        background's ``features`` under the ``backgrounds`` namespace, so a
        feature write must invalidate it in addition to the
        ``nested_features`` purge the shared mixin already does.
        """

        response = await super()._mutate_feature(source, source_type, mutate)
        await invalidate_background_cache()
        return response
