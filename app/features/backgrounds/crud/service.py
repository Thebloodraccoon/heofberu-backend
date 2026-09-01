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

    Capability services are composed explicitly in ``__init__`` (no mixin
    MRO): ``get_by_id`` reads the BACKGROUND-source ``features`` through
    :class:`BackgroundFeatureService` and assembles :class:`BackgroundFullResponse`;
    ``create_background`` seeds ``granted_skills`` through
    :class:`BackgroundSkillsService` in the same ``_atomic()`` transaction.
    """

    repository: BackgroundRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Compose the feature and skill capability services."""

        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )
        self._features = BackgroundFeatureService(db)
        self._skills = BackgroundSkillsService(db)

    async def create_background(self, background_data: BackgroundCreate) -> BackgroundResponse:
        """Create a background after checking its name isn't already taken."""

        skills = await self._skills.resolve_skills(background_data.granted_skills)

        payload = background_data.model_dump(exclude={"granted_skills"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if skills:
                await self._skills.set_skills_for_background(item, skills, commit=False)

        await invalidate_background_cache()
        response = await self._get_response(item.id)

        # Warm the cache immediately: the write already paid for the transaction,
        # so the next GET hits cache instead of racing the invalidation.
        await self.get_by_id(item.id)

        return response

    @use_cache()
    async def get_by_id(self, item_id: int) -> BackgroundFullResponse:
        """
        Return a background with its own BACKGROUND-source ``features`` included.

        Overrides ``BaseService.get_by_id`` so ``GET /backgrounds/{id}`` is the
        full picture — base fields, skills, items, and features — cached as a
        single unit. Any write invalidates the whole background namespaces.
        """

        background = await self._get_or_404(item_id)
        features = await self._features.list_features(item_id)

        return BackgroundFullResponse.model_validate(
            {**BackgroundResponse.model_validate(background).model_dump(), "features": features}
        )
