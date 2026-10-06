"""Spell-specific application exceptions."""

from app.core.exceptions import AppError


class SpellNotFoundException(AppError):
    """Raised when a spell with the given ID or name does not exist."""

    status_code = 404

    def __init__(self, spell_id: int | None = None, name: str | None = None):
        """Build the 404 message from the optional spell ID or name."""

        detail = "Spell is not found"

        if spell_id:
            detail = f"Spell with ID {spell_id} is not found."

        if name:
            detail = f"Spell with name '{name}' is not found."

        super().__init__(detail)
