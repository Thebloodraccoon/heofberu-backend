"""Background suggestions service: list and per-item CRUD on the personality-card suggestion pool."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BackgroundSuggestionType
from app.core.exceptions import RecordNotFoundError
from app.features.backgrounds.capability import BackgroundCapabilityService
from app.features.backgrounds.suggestions.exceptions import LastSuggestionOfTypeError, SuggestionNotFoundException
from app.features.backgrounds.suggestions.repository import BackgroundSuggestionsRepository
from app.features.backgrounds.suggestions.schemas import SuggestionCreate, SuggestionResponse, SuggestionUpdate
from app.models import BackgroundSuggestion


class BackgroundSuggestionsService(BackgroundCapabilityService):
    """
    Background suggestion pool: listing plus per-suggestion create/update/delete.

    Character creation needs exactly one suggestion per
    :class:`BackgroundSuggestionType`, so the last suggestion of a type can be
    neither deleted nor re-typed (409).
    """

    repository: BackgroundSuggestionsRepository

    def __init__(self, db: AsyncSession):
        """Initialize the service with the suggestions repository."""

        super().__init__(BackgroundSuggestionsRepository(db))

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
        """Edit a single existing suggestion (re-typing the last one of its type is refused)."""

        async with self._atomic():
            suggestion = await self._lock_and_get_suggestion(background_id, suggestion_id)

            new_type = data.suggestion_type
            if new_type is not None and new_type != suggestion.suggestion_type:
                await self._ensure_not_last_of_type(suggestion)

            updated = await self.repository.update_suggestion(suggestion, data, commit=False)
            await self._invalidate_cache()

        return SuggestionResponse.model_validate(updated)

    async def delete_suggestion(self, background_id: int, suggestion_id: int) -> None:
        """Remove a single suggestion (refused when it is the last one of its type)."""

        async with self._atomic():
            suggestion = await self._lock_and_get_suggestion(background_id, suggestion_id)
            await self._ensure_not_last_of_type(suggestion)

            await self.repository.delete_suggestion(suggestion, commit=False)
            await self._invalidate_cache()

    async def _lock_and_get_suggestion(self, background_id: int, suggestion_id: int) -> BackgroundSuggestion:
        """Lock the background (serializes concurrent last-of-type checks) and fetch its suggestion, or 404."""

        if not await self.repository.lock_background(background_id):
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(background_id))

        suggestion = await self.repository.get_suggestion(background_id, suggestion_id)
        if not suggestion:
            raise SuggestionNotFoundException(background_id=background_id, suggestion_id=suggestion_id)

        return suggestion

    async def _ensure_not_last_of_type(self, suggestion: BackgroundSuggestion) -> None:
        """Raise ``LastSuggestionOfTypeError`` unless another suggestion of the same type remains."""

        suggestion_type = BackgroundSuggestionType(suggestion.suggestion_type)
        if await self.repository.count_of_type(suggestion.background_id, suggestion_type) <= 1:
            raise LastSuggestionOfTypeError(suggestion.background_id, suggestion_type.value)
