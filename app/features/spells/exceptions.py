from fastapi import HTTPException, status


class SpellNotFoundException(HTTPException):
    def __init__(self, spell_id: int | None = None, name: str | None = None):
        detail = "Spell is not found"

        if spell_id:
            detail = f"Spell with ID {spell_id} is not found."

        if name:
            detail = f"Spell with name '{name}' is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class InvalidClassIdsException(HTTPException):
    """Raised when one or more provided class IDs do not correspond to existing classes."""

    def __init__(self, class_ids: list[int]):
        self.class_ids = class_ids
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid class id(s): {class_ids}",
        )


class InvalidRaceIdsException(HTTPException):
    """Raised when one or more provided race IDs do not correspond to existing races."""

    def __init__(self, race_ids: list[int]):
        self.race_ids = race_ids
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid race id(s): {race_ids}",
        )
