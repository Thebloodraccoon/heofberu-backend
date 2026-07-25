from fastapi import HTTPException, status


class RaceNotFoundException(HTTPException):
    def __init__(self, race_id: int | None = None, name: str | None = None):
        detail = "Race is not found"

        if race_id:
            detail = f"Race with ID {race_id} is not found."

        if name:
            detail = f"Race with name '{name}' is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class RaceNameAlreadyExistsException(HTTPException):
    def __init__(self, name: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Race with name '{name}' already exists.",
        )
