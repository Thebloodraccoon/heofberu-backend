from fastapi import HTTPException, status


class CharacterNotFoundException(HTTPException):
    def __init__(self, character_id: int | None = None):
        detail = "Character is not found"

        if character_id:
            detail = f"Character with ID {character_id} is not found."

        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class CharacterAccessDeniedException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this character.",
        )
