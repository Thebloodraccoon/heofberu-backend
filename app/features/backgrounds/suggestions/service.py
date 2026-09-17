"""Background suggestions service: list and per-item CRUD on the personality-card suggestion pool."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.backgrounds.cache import BACKGROUND_CACHE_NAMESPACES
from app.features.backgrounds.crud.schemas import BackgroundCreate, BackgroundResponse, BackgroundUpdate
from app.features.backgrounds.suggestions.exceptions import SuggestionNotFoundException
from app.features.backgrounds.suggestions.repository import BackgroundSuggestionsRepository
from app.features.backgrounds.suggestions.schemas import (
    SuggestionCreate,
    SuggestionEntry,
    SuggestionResponse,
    SuggestionUpdate,
)
from app.models import Background, BackgroundSuggestion


class BackgroundSuggestionsService(
    BaseService[Background, BackgroundCreate, BackgroundUpdate, BackgroundResponse, None]
):
    """
    Background suggestion pool: listing plus per-suggestion create/update/delete.

    Composed into :class:`BackgroundCrudService` for creation-time bulk seeding
    (``set_suggestions_for_background``); the public endpoints operate on one
    suggestion at a time.
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

        await self._exists_or_404(background_id)
        rows = await self.repository.list_suggestions(background_id)
        return [SuggestionResponse.model_validate(row) for row in rows]

    async def create_suggestion(self, background_id: int, data: SuggestionCreate) -> SuggestionResponse:
        """Add a single suggestion to the background."""

        await self._exists_or_404(background_id)
        row = await self.repository.create_suggestion(background_id, data)
        await self._invalidate_cache()

        return SuggestionResponse.model_validate(row)

    async def update_suggestion(
        self, background_id: int, suggestion_id: int, data: SuggestionUpdate
    ) -> SuggestionResponse:
        """Edit a single existing suggestion."""

        await self._exists_or_404(background_id)
        suggestion = await self._get_suggestion_or_404(background_id, suggestion_id)
        updated = await self.repository.update_suggestion(suggestion, data)
        await self._invalidate_cache()

        return SuggestionResponse.model_validate(updated)

    async def delete_suggestion(self, background_id: int, suggestion_id: int) -> None:
        """Remove a single suggestion from the background."""

        await self._exists_or_404(background_id)
        suggestion = await self._get_suggestion_or_404(background_id, suggestion_id)
        await self.repository.delete_suggestion(suggestion)
        await self._invalidate_cache()

    async def set_suggestions_for_background(
        self, background: Background, suggestions: list[SuggestionEntry], *, commit: bool = True
    ) -> None:
        """Attach ``suggestions`` to a ``background`` row (used by ``create_background``)."""

        await self.repository.set_suggestions(background, suggestions, commit=commit)

    async def _get_suggestion_or_404(self, background_id: int, suggestion_id: int) -> BackgroundSuggestion:
        """Fetch a suggestion scoped to the background, or raise ``SuggestionNotFoundException``."""

        suggestion = await self.repository.get_suggestion(background_id, suggestion_id)
        if not suggestion:
            raise SuggestionNotFoundException(background_id=background_id, suggestion_id=suggestion_id)

        return suggestion
