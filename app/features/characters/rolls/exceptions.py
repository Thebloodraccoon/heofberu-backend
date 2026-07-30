from fastapi import HTTPException, status


class InvalidRollRequestException(HTTPException):
    """
    Raised when a roll-check/roll-attack request is malformed (e.g. neither
    skill_id nor ability provided, or an unrecognized check type).
    """

    def __init__(self, message: str = "Invalid roll request."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
