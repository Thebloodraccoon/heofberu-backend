"""Background suggestions repository: per-background listing and per-suggestion CRUD."""

from sqlalchemy import func, select

from app.constants import BackgroundSuggestionType
from app.features.backgrounds.crud.repository import BackgroundRepository
from app.features.backgrounds.suggestions.schemas import SuggestionCreate, SuggestionEntry, SuggestionUpdate
from app.models import Background, BackgroundSuggestion


class BackgroundSuggestionsRepository(BackgroundRepository):
    """Suggestion persistence for backgrounds, layered on :class:`BackgroundRepository`."""

    async def list_suggestions(self, background_id: int) -> list[BackgroundSuggestion]:
        """Return every suggestion row owned by the background, ordered by type then id."""

        result = await self.db.execute(
            select(BackgroundSuggestion)
            .where(BackgroundSuggestion.background_id == background_id)
            .order_by(BackgroundSuggestion.suggestion_type, BackgroundSuggestion.id)
        )
        return list(result.scalars().all())

    async def get_suggestion(self, background_id: int, suggestion_id: int) -> BackgroundSuggestion | None:
        """Fetch a single suggestion scoped to the background, or ``None``."""

        result = await self.db.execute(
            select(BackgroundSuggestion).where(
                BackgroundSuggestion.id == suggestion_id,
                BackgroundSuggestion.background_id == background_id,
            )
        )
        return result.scalar_one_or_none()

    async def lock_background(self, background_id: int) -> bool:
        """Lock the background row for the rest of the transaction; ``False`` when it doesn't exist."""

        locked = await self.db.scalar(select(Background.id).where(Background.id == background_id).with_for_update())
        return locked is not None

    async def count_of_type(self, background_id: int, suggestion_type: BackgroundSuggestionType) -> int:
        """Count the background's suggestions of one type."""

        stmt = (
            select(func.count())
            .select_from(BackgroundSuggestion)
            .where(
                BackgroundSuggestion.background_id == background_id,
                BackgroundSuggestion.suggestion_type == suggestion_type,
            )
        )
        return (await self.db.scalar(stmt)) or 0

    async def create_suggestion(
        self, background_id: int, data: SuggestionCreate, *, commit: bool = True
    ) -> BackgroundSuggestion:
        """Add a single suggestion to the background."""

        row = BackgroundSuggestion(background_id=background_id, suggestion_type=data.suggestion_type, text=data.text)
        self.db.add(row)
        await self.commit_or_flush(commit=commit)

        return row

    async def update_suggestion(
        self, suggestion: BackgroundSuggestion, data: SuggestionUpdate, *, commit: bool = True
    ) -> BackgroundSuggestion:
        """Apply the given fields to an existing suggestion."""

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(suggestion, field, value)

        await self.commit_or_flush(commit=commit)

        return suggestion

    async def delete_suggestion(self, suggestion: BackgroundSuggestion, *, commit: bool = True) -> None:
        """Remove a single suggestion."""

        await self.db.delete(suggestion)
        await self.commit_or_flush(commit=commit)

    async def set_suggestions(
        self, background: Background, suggestions: list[SuggestionEntry], *, commit: bool = True
    ) -> list[BackgroundSuggestion]:
        """Seed the background's suggestions in bulk (used at creation time only)."""

        rows = [
            BackgroundSuggestion(background_id=background.id, suggestion_type=entry.suggestion_type, text=entry.text)
            for entry in suggestions
        ]
        self.db.add_all(rows)

        await self.commit_or_flush(commit=commit)

        return rows
