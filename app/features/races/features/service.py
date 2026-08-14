"""Race feature service: per-source feature CRUD, atomic with character reconciliation."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.races.crud.repository import RaceRepository
from app.features.races.schemas import RaceCreate, RaceResponse, RaceUpdate
from app.features.shared.features.mixins import SourceFeatureMixin
from app.features.shared.features.nested_service import NestedFeatureService
from app.models.race_model import Race


class RaceFeatureService(
    SourceFeatureMixin,
    BaseService[Race, RaceCreate, RaceUpdate, RaceResponse, None],
):
    """
    Everything about a race's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    come from :class:`SourceFeatureMixin`, which owns the row-level
    source-ownership rules, the source existence check (``_get_or_404``),
    and the ``_atomic()`` transaction that also runs character-grant
    reconciliation. The generic CRUD machinery comes from
    :class:`BaseService`.

    ``RaceResponse`` does not embed the race's features (read via
    ``GET /races/{id}/features`` under the ``nested_features`` cache), so
    feature writes only purge that namespace — the shared mixin's default
    behavior, no override needed here.
    """

    repository: RaceRepository

    _feature_source_type = FeatureSourceType.RACE

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
        )
        self._features = NestedFeatureService(db)
