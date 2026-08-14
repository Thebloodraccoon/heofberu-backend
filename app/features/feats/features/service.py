"""Feat feature service: per-source feature CRUD, atomic with character reconciliation."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.feats.cache import invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.schemas import FeatCreate, FeatResponse, FeatUpdate
from app.features.shared.features.mixins import SourceFeatureMixin
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import NestedFeatureResponse
from app.models.feat_model import Feat


class FeatFeatureService(
    SourceFeatureMixin,
    BaseService[Feat, FeatCreate, FeatUpdate, FeatResponse, None],
):
    """
    Everything about a feat's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    come from :class:`SourceFeatureMixin`, which owns the row-level
    source-ownership rules, the source existence check (``_get_or_404``),
    and the ``_atomic()`` transaction that also runs character-grant
    reconciliation. The generic CRUD machinery comes from
    :class:`BaseService`.

    The one feat-specific bit the shared engine deliberately does not do: a
    feature write also purges the ``feats`` cache namespace, because
    ``FeatFullResponse`` embeds ``features`` (see :meth:`_mutate_feature`).
    """

    repository: FeatRepository

    _feature_source_type = FeatureSourceType.FEAT

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
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
        the ``feats`` cache namespace too.

        ``FeatFullResponse`` (``GET /feats/{id}``) embeds the feat's
        ``features`` under the ``feats`` namespace, so a feature write must
        invalidate it in addition to the ``nested_features`` purge the
        shared mixin already does.
        """

        response = await super()._mutate_feature(source, source_type, mutate)
        await invalidate_feat_cache()
        return response
