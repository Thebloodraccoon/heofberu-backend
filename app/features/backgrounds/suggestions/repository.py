"""Background suggestions repository: per-background listing and full replacement."""

from sqlalchemy import delete, select

from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.suggestions.schemas import SuggestionEntry
from app.models import Background, BackgroundSuggestion


class BackgroundSuggestionsRepository(BackgroundRepository):
    """Suggestion persistence for backgrounds, layered on :class:`BackgroundRepository`."""

    async def list_suggestions(self, background_id: int) -> list[BackgroundSuggestion]:
        """Return every suggestion row owned by the background, ordered by id."""

        result = await self.db.execute(
            select(BackgroundSuggestion)
            .where(BackgroundSuggestion.background_id == background_id)
            .order_by(BackgroundSuggestion.id)
        )
        return list(result.scalars().all())

    async def set_suggestions(
        self, background: Background, suggestions: list[SuggestionEntry], *, commit: bool = True
    ) -> list[BackgroundSuggestion]:
        """Fully replace a background's suggestions (delete + insert)."""

        await self.db.execute(delete(BackgroundSuggestion).where(BackgroundSuggestion.background_id == background.id))

        rows = [
            BackgroundSuggestion(background_id=background.id, suggestion_type=entry.suggestion_type, text=entry.text)
            for entry in suggestions
        ]
        self.db.add_all(rows)

        await self.commit_or_flush(commit=commit)

        return rows
