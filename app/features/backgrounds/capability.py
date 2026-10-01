"""Shared base for the per-capability background services (skills, tags, items, suggestions, features)."""

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.models import Background


class BackgroundCapabilityService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None]
):
    """
    A capability endpoint's service: it writes one slice of a background and
    answers with the full :class:`BackgroundResponse`.

    Create/update schemas are irrelevant here; the generics only exist so the
    inherited ``_exists_or_404`` / ``_get_response`` / ``_invalidate_cache``
    helpers are typed once for every capability.
    """

    repository: BackgroundRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, repository: BackgroundRepository):
        """Bind the capability's repository and the shared response schema."""

        super().__init__(repository=repository, response_schema=BackgroundResponse)
