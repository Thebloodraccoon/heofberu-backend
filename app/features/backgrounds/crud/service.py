"""Background CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BackgroundSuggestionType
from app.core.base.cached_service import CachedService
from app.core.cache import use_cache
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES, invalidate_background_cache
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import (
    BackgroundCreate,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
)
from app.features.backgrounds.features.service import BackgroundFeatureService
from app.features.backgrounds.suggestions.schemas import SuggestionEntry
from app.features.backgrounds.suggestions.service import BackgroundSuggestionsService
from app.models import Background

#: Placeholder text seeded for each automatically created suggestion.
BACKGROUND_DEFAULT_SUGGESTION_TEXT = "-"


class BackgroundCrudService(
    CachedService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundGetAllResponse]
):
    """
    Background catalog CRUD built on :class:`CachedService`.

    ``get_by_id`` reads the BACKGROUND-source ``features`` through
    :class:`BackgroundFeatureService` (composed explicitly in ``__init__``,
    no mixin MRO) and folds them into :class:`BackgroundResponse`.
    ``granted_skills``/``starting_items``/``features`` are deliberately not
    seeded at create time — each is attached afterwards through its own
    capability endpoint. ``suggestions`` ARE seeded: one placeholder row
    (``text="-"``) per :class:`BackgroundSuggestionType`, so a fresh
    background immediately satisfies character creation's one-id-per-type
    contract.
    """

    repository: BackgroundRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Compose the capability services (features + suggestions)."""

        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )
        self._features = BackgroundFeatureService(db)
        self._suggestions = BackgroundSuggestionsService(db)

    async def create_background(self, background_data: BackgroundCreate) -> BackgroundResponse:
        """Create a background, seeding its 4 default placeholder suggestions in the same transaction."""

        async with self._atomic():
            item = await self.repository.create(background_data.model_dump(), commit=False)
            await self._suggestions.set_suggestions_for_background(
                item,
                [
                    SuggestionEntry(suggestion_type=suggestion_type, text=BACKGROUND_DEFAULT_SUGGESTION_TEXT)
                    for suggestion_type in BackgroundSuggestionType
                ],
                commit=False,
            )

        await invalidate_background_cache()

        return await self.get_by_id(item.id)

    @use_cache()
    async def get_by_id(self, item_id: int) -> BackgroundResponse:
        """
        Return a background with its own BACKGROUND-source ``features`` included.

        Overrides ``BaseService.get_by_id`` so ``GET /backgrounds/{id}`` is the
        full picture — base fields, skills, items, suggestions, and features —
        cached as a single unit. Any write invalidates the whole background
        namespaces.
        """

        background = await self._get_or_404(item_id)
        features = await self._features.list_features(item_id)

        return BackgroundResponse.model_validate(
            {**BackgroundResponse.model_validate(background).model_dump(), "features": features}
        )
