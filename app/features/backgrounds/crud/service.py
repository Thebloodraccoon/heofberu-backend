"""Background CRUD service: cached catalog CRUD plus the creation-time suggestion seeding."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BackgroundSuggestionType
from app.core.base.cached_service import CachedService
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES, BACKGROUND_DELETE_CACHE_NAMESPACES
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.crud.schemas import (
    BackgroundCreate,
    BackgroundGetAllResponse,
    BackgroundResponse,
    BackgroundUpdate,
)
from app.features.backgrounds.suggestions.repository import BackgroundSuggestionsRepository
from app.features.backgrounds.suggestions.schemas import SuggestionEntry
from app.models import Background

#: Placeholder text seeded for each automatically created suggestion.
BACKGROUND_DEFAULT_SUGGESTION_TEXT = "-"


class BackgroundCrudService(
    CachedService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, BackgroundGetAllResponse]
):
    """
    Background catalog CRUD built on :class:`CachedService`.

    ``get_by_id`` is the full picture (skills, items, suggestions, tags and
    the BACKGROUND-source ``features``), cached as one unit. Only the
    suggestions are seeded at create time: one placeholder row
    (``text="-"``) per :class:`BackgroundSuggestionType`, so a fresh
    background immediately satisfies character creation's one-id-per-type
    contract. Skills, items, tags and features are attached afterwards
    through their own capability endpoints.
    """

    repository: BackgroundRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Set up the background repository and the suggestion seeder."""

        super().__init__(
            repository=BackgroundRepository(db),
            response_schema=BackgroundResponse,
            get_all_schema=BackgroundGetAllResponse,
        )
        self._suggestions = BackgroundSuggestionsRepository(db)

    async def create_background(self, background_data: BackgroundCreate) -> BackgroundResponse:
        """Create a background and its 4 default placeholder suggestions in one transaction."""

        async with self._atomic():
            item = await self.repository.create(background_data.model_dump(), commit=False)
            await self._suggestions.set_suggestions(
                item,
                [
                    SuggestionEntry(suggestion_type=suggestion_type, text=BACKGROUND_DEFAULT_SUGGESTION_TEXT)
                    for suggestion_type in BackgroundSuggestionType
                ],
                commit=False,
            )
            await self._invalidate_cache()

        return await self.get_by_id(item.id)

    @use_cache()
    async def get_by_id(self, item_id: int) -> BackgroundResponse:
        """Return the full background; the eager load already carries its BACKGROUND-source features."""

        return await self._get_response(item_id)

    async def delete(self, item_id: int) -> bool:
        """Delete a background (blocked while a feature of it is granted to a character)."""

        background = await self.repository.get_bare(item_id)
        if background is None:
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(item_id))

        result = await self.repository.delete(background)
        await invalidate_after_commit(self.repository.db, *BACKGROUND_DELETE_CACHE_NAMESPACES)

        return result
