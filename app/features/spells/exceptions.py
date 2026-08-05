"""Spell-specific HTTP exceptions."""

from fastapi import HTTPException, status


class SpellNotFoundException(HTTPException):
    """Raised when a spell with the given ID or name does not exist."""

    def __init__(self, spell_id: int | None = None, name: str | None = None):
        detail = "Spell is not found"

        if spell_id:
            detail = f"Spell with ID {spell_id} is not found."

        if name:
            detail = f"Spell with name '{name}' is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
