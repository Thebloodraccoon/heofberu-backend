from fastapi import HTTPException, status


class InvalidHpUpdateException(HTTPException):
    """
    Raised when an HP update request is malformed (e.g. mixes delta with
    absolute values, or provides neither).
    """

    def __init__(self, message: str = "Provide either 'delta' or an absolute HP value, not both."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class InvalidRestTypeException(HTTPException):
    """Raised when the rest type is not one of the supported values."""

    def __init__(self, rest_type: str):
        self.rest_type = rest_type
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rest type: '{rest_type}'. Expected 'short' or 'long'.",
        )
