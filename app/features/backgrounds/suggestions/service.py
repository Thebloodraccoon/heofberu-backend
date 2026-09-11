"""Background suggestions service: list and full-replace the personality-card suggestion pool."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.backgrounds.suggestions.repository import BackgroundSuggestionsRepository
from app.features.backgrounds.suggestions.schemas import SuggestionEntry, SuggestionResponse, SuggestionsUpdate
from app.models import Background


class BackgroundSuggestionsService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None]
):
    """
    Background suggestion pool: full listing and full replacement.

    Mirrors :class:`BackgroundSkillsService`'s shape (a capability service
    composed into :class:`BackgroundCrudService` for creation-time seeding,
    plus its own PUT full-replace endpoint).
    """

    repository: BackgroundSuggestionsRepository

    cache_namespaces = BACKGROUND_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the suggestions repository."""

        super().__init__(
            repository=BackgroundSuggestionsRepository(db),
            response_schema=BackgroundResponse,
        )

    async def list_suggestions(self, background_id: int) -> list[SuggestionResponse]:
        """Return every suggestion for the background."""

        await self._get_or_404(background_id)
        rows = await self.repository.list_suggestions(background_id)
        return [SuggestionResponse.model_validate(row) for row in rows]

    async def set_suggestions(self, background_id: int, data: SuggestionsUpdate) -> list[SuggestionResponse]:
        """Fully replace the background's suggestions."""

        background = await self._get_or_404(background_id)
        rows = await self.repository.set_suggestions(background, data.suggestions)
        await self._invalidate_cache()

        return [SuggestionResponse.model_validate(row) for row in rows]

    async def set_suggestions_for_background(
        self, background: Background, suggestions: list[SuggestionEntry], *, commit: bool = True
    ) -> None:
        """Attach ``suggestions`` to a ``background`` row (used by ``create_background``)."""

        await self.repository.set_suggestions(background, suggestions, commit=commit)
