"""Exceptions for the character core sub-domain."""

from fastapi import HTTPException, status


class InvalidHpUpdateException(HTTPException):
    """
    Raised when an HP update request is malformed (e.g. mixes delta with
    absolute values, or provides neither).
    """

    def __init__(self, message: str = "Provide either 'delta' or an absolute HP value, not both."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
