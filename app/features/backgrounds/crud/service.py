"""Background CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.cache import use_cache
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES, invalidate_background_cache
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import (
    BackgroundCreate,
    BackgroundFullResponse,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
)
from app.features.backgrounds.features.service import BackgroundFeatureService
from app.features.backgrounds.skills.service import BackgroundSkillsService
from app.models import Background


class BackgroundCrudService(
    CachedService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundGetAllResponse]
):
    """
    Background catalog CRUD built on :class:`CachedService`.

    The capability services are composed explicitly in ``__init__`` (no
    mixin MRO):
      - ``get_by_id`` reads the BACKGROUND-source ``features`` through
        :class:`BackgroundFeatureService` — the cached nested listing —
        and assembles :class:`BackgroundFullResponse`;
        ``granted_skills``/``starting_items`` come from the repository's
        eager loads;
      - ``create_background`` seeds ``granted_skills`` through
        :class:`BackgroundSkillsService` in the same ``_atomic()``
        transaction.

    ``cache_namespaces`` covers the three namespaces any background read
    hits (the same blunt whole-namespace invalidation the previous
    service used); the capability services use
    :func:`invalidate_background_cache` explicitly for their own writes.
    """

    repository: BackgroundRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )
        self._features = BackgroundFeatureService(db)
        self._skills = BackgroundSkillsService(db)

    async def create_background(self, background_data: BackgroundCreate) -> BackgroundResponse:
        """
        Create a background after checking its name isn't already taken.

        Kept minimal on purpose: only the background's own scalar fields
        plus ``granted_skills`` (a simple association, not a nested
        dependency) are set here, atomically, alongside the ``Background``
        row itself.

        ``features`` and ``starting_items`` are NOT part of create —
        attach them afterwards through their own endpoints:
          - ``POST /backgrounds/{id}/features``
          - ``PUT /backgrounds/{id}/items``
        """

        skills = await self._skills.resolve_skills(background_data.granted_skills)

        payload = background_data.model_dump(exclude={"granted_skills"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if skills:
                await self._skills.set_skills_for_background(item, skills, commit=False)

        await invalidate_background_cache()
        response = await self._get_response(item.id)

        # Warm the cache immediately: the write already paid for the
        # transaction, so pre-populating it here means the very next GET
        # (which is likely right after a create) hits cache instead of
        # racing the invalidation into a cold read.
        await self.get_by_id(item.id)

        return response

    @use_cache()
    async def get_by_id(self, item_id: int) -> BackgroundFullResponse:
        """
        Return a background with its own BACKGROUND-source ``features``
        included — this overrides ``BaseService.get_by_id`` (which only
        returns bare ``BackgroundResponse`` fields via a plain
        ``model_validate``) so ``GET /backgrounds/{id}`` itself is the
        full picture: base fields, granted_skills, starting_items, and
        features.

        This exists so a client that needs the whole background gets it
        from the one endpoint it would already call, cached as a single
        unit, instead of a separate call to ``.../features`` — its own
        cache entry that would need to warm up independently.

        Any write that touches this background (base fields, granted
        skills, features, starting items) invalidates the ``backgrounds``
        namespace — plus ``background_features``, ``features`` and
        ``nested_items`` via :func:`invalidate_background_cache` — the
        same blunt, whole-namespace invalidation the rest of this service
        uses for reference-catalog data (infrequent writes, frequent
        reads).
        """

        background = await self._get_or_404(item_id)
        features = await self._features.list_features(item_id)

        return BackgroundFullResponse.model_validate(
            {**BackgroundResponse.model_validate(background).model_dump(), "features": features}
        )
