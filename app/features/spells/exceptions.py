from fastapi import HTTPException, status


class SpellNotFoundException(HTTPException):
    def __init__(self, spell_id: int | None = None, name: str | None = None):
        detail = "Spell is not found"

        if spell_id:
            detail = f"Spell with ID {spell_id} is not found."

        if name:
            detail = f"Spell with name '{name}' is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class SpellNameAlreadyExistsException(HTTPException):
    def __init__(self, name: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Spell with name '{name}' already exists.",
        )
